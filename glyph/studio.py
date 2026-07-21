from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Any
from urllib.parse import parse_qs, urlparse
import webbrowser

from .compiler import GlyphError
from .incremental import IncrementalCompiler


@dataclass(frozen=True)
class StudioSnapshot:
    version: int
    status: str
    source: str
    digest: str
    updated_at: str
    diagnostics: tuple[dict[str, object], ...]
    artifacts: dict[str, str]
    semantic: dict[str, object]
    execution_ir: dict[str, object]

    def to_dict(self, source_path: Path, output_dir: Path) -> dict[str, object]:
        return {
            "version": self.version,
            "status": self.status,
            "source": self.source,
            "source_path": str(source_path),
            "output_dir": str(output_dir),
            "digest": self.digest,
            "updated_at": self.updated_at,
            "diagnostics": list(self.diagnostics),
            "artifact_names": sorted(self.artifacts),
            "semantic": self.semantic,
            "execution_ir": self.execution_ir,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _source_digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


class GlyphStudio:
    """One-process development environment for one Glyph source file."""

    def __init__(self, input_path: str | Path):
        self.input_path = Path(input_path).resolve()
        self.output_dir = self.input_path.parent / ".glyph" / self.input_path.stem
        self.compiler = IncrementalCompiler()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._watcher: threading.Thread | None = None
        self._snapshot = StudioSnapshot(
            version=0,
            status="starting",
            source="",
            digest="",
            updated_at=_utc_now(),
            diagnostics=(),
            artifacts={},
            semantic={},
            execution_ir={},
        )

    @property
    def snapshot(self) -> StudioSnapshot:
        with self._lock:
            return self._snapshot

    def state_dict(self) -> dict[str, object]:
        with self._lock:
            return self._snapshot.to_dict(self.input_path, self.output_dir)

    def artifact(self, name: str) -> str | None:
        with self._lock:
            return self._snapshot.artifacts.get(name)

    def rebuild(self, source: str | None = None) -> StudioSnapshot:
        if source is None:
            source = self.input_path.read_text(encoding="utf-8")
        digest = _source_digest(source)
        previous = self.snapshot
        if previous.status == "ready" and previous.digest == digest:
            return previous

        try:
            result = self.compiler.compile_text(
                source,
                source_name=str(self.input_path),
                source_href=str(self.input_path),
            )
            compilation = result.snapshot
            artifacts = {
                "generated.rs": compilation.artifacts.logic,
                "host.generated.rs": compilation.artifacts.host,
                "typed-ast.json": compilation.semantic_json,
                **compilation.diagrams.files,
            }
            for name, content in artifacts.items():
                _atomic_write(self.output_dir / name, content)
            semantic = json.loads(compilation.semantic_json)
            execution_ir = compilation.diagrams.ir.to_dict()
            snapshot = StudioSnapshot(
                version=previous.version + 1,
                status="ready",
                source=source,
                digest=digest,
                updated_at=_utc_now(),
                diagnostics=(),
                artifacts=artifacts,
                semantic=semantic,
                execution_ir=execution_ir,
            )
        except (GlyphError, OSError, ValueError) as exc:
            snapshot = StudioSnapshot(
                version=previous.version + 1,
                status="error",
                source=source,
                digest=digest,
                updated_at=_utc_now(),
                diagnostics=({"severity": "error", "message": str(exc)},),
                artifacts=previous.artifacts,
                semantic=previous.semantic,
                execution_ir=previous.execution_ir,
            )

        with self._lock:
            self._snapshot = snapshot
        return snapshot

    def save_source(self, source: str) -> StudioSnapshot:
        _atomic_write(self.input_path, source)
        return self.rebuild(source)

    def start_watching(self, interval: float = 0.35) -> None:
        if self._watcher is not None and self._watcher.is_alive():
            return
        self._stop.clear()

        def watch() -> None:
            last_seen = ""
            while not self._stop.wait(interval):
                try:
                    source = self.input_path.read_text(encoding="utf-8")
                except OSError as exc:
                    with self._lock:
                        current = self._snapshot
                        self._snapshot = StudioSnapshot(
                            version=current.version + 1,
                            status="error",
                            source=current.source,
                            digest=current.digest,
                            updated_at=_utc_now(),
                            diagnostics=({"severity": "error", "message": str(exc)},),
                            artifacts=current.artifacts,
                            semantic=current.semantic,
                            execution_ir=current.execution_ir,
                        )
                    continue
                digest = _source_digest(source)
                if digest == last_seen:
                    continue
                last_seen = digest
                self.rebuild(source)

        self._watcher = threading.Thread(
            target=watch,
            name="glyph-studio-watch",
            daemon=True,
        )
        self._watcher.start()

    def stop(self) -> None:
        self._stop.set()
        if self._watcher is not None:
            self._watcher.join(timeout=1.0)

    def create_server(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> ThreadingHTTPServer:
        studio = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "GlyphStudio/1"

            def log_message(self, format: str, *args: object) -> None:
                return

            def _json(
                self,
                value: object,
                status: HTTPStatus = HTTPStatus.OK,
            ) -> None:
                payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)

            def _body(self) -> dict[str, Any]:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length) if length else b"{}"
                    value = json.loads(raw.decode("utf-8"))
                    return value if isinstance(value, dict) else {}
                except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                    return {}

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    payload = STUDIO_HTML.encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                if parsed.path == "/api/state":
                    self._json(studio.state_dict())
                    return
                if parsed.path == "/api/artifact":
                    name = parse_qs(parsed.query).get("name", [""])[0]
                    artifact = studio.artifact(name)
                    if artifact is None:
                        self._json(
                            {"error": "unknown artifact"},
                            HTTPStatus.NOT_FOUND,
                        )
                    else:
                        self._json({"name": name, "content": artifact})
                    return
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                if self.path == "/api/save":
                    body = self._body()
                    source = body.get("source")
                    if not isinstance(source, str):
                        self._json(
                            {"error": "source must be text"},
                            HTTPStatus.BAD_REQUEST,
                        )
                        return
                    studio.save_source(source)
                    self._json(studio.state_dict())
                    return
                if self.path == "/api/rebuild":
                    studio.rebuild()
                    self._json(studio.state_dict())
                    return
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        return ThreadingHTTPServer((host, port), Handler)

    def serve(self, *, open_browser: bool = True) -> int:
        self.rebuild()
        self.start_watching()
        server = self.create_server(
            port=int(os.environ.get("GLYPH_STUDIO_PORT", "0"))
        )
        host, port = server.server_address[:2]
        url = f"http://{host}:{port}/"
        print(f"Glyph Studio: {url}")
        print(f"Source: {self.input_path}")
        print("終了: Ctrl+C")
        if open_browser and os.environ.get("GLYPH_STUDIO_NO_BROWSER") != "1":
            threading.Timer(0.15, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
            self.stop()
        return 0


STUDIO_HTML = r'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Glyph Studio</title>
<style>
:root{color-scheme:dark;--bg:#111318;--panel:#191c23;--line:#303540;--text:#e9edf4;--muted:#97a0b2;--ok:#63d5a4;--bad:#ff7c8d;--accent:#88a8ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 ui-sans-serif,system-ui,sans-serif;height:100vh;overflow:hidden}
header{height:58px;display:flex;align-items:center;gap:14px;padding:0 18px;border-bottom:1px solid var(--line);background:#14171d}
.brand{font-weight:750;font-size:17px}.path{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}.status{padding:5px 9px;border-radius:999px;background:#252a34}.status.ready{color:var(--ok)}.status.error{color:var(--bad)}
button{border:1px solid var(--line);background:#252a34;color:var(--text);border-radius:7px;padding:7px 11px;cursor:pointer}button.primary{background:#3658a7;border-color:#5276cf}button:hover{filter:brightness(1.12)}
main{height:calc(100vh - 58px);display:grid;grid-template-columns:minmax(350px,46%) 1fr}.editor-pane{border-right:1px solid var(--line);display:flex;flex-direction:column;min-width:0}.pane-title{height:42px;padding:11px 14px;color:var(--muted);border-bottom:1px solid var(--line)}
textarea{flex:1;width:100%;resize:none;border:0;outline:0;background:#101217;color:#e6ebf3;padding:16px;font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;tab-size:2}
.viewer{min-width:0;display:flex;flex-direction:column}.tabs{height:42px;display:flex;gap:2px;padding:5px 8px;border-bottom:1px solid var(--line);overflow-x:auto}.tab{background:transparent;border:0;color:var(--muted);white-space:nowrap}.tab.active{color:var(--text);background:#252a34}.content{flex:1;overflow:auto;padding:18px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.card{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:13px}.value{font-size:24px;font-weight:700}.label{color:var(--muted)}
pre{white-space:pre-wrap;word-break:break-word;background:#101217;border:1px solid var(--line);border-radius:8px;padding:14px;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace}.error{border:1px solid #743844;background:#26171b;color:#ffc2ca;padding:12px;border-radius:8px;margin-bottom:12px}
.machine{display:flex;align-items:center;gap:10px;overflow:auto;padding:14px 4px}.state{min-width:130px;text-align:center;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:13px}.state.initial{border-color:var(--accent)}.state.success{border-color:var(--ok)}.state.failure{border-color:var(--bad)}.arrow{color:var(--muted);font-size:20px}.transition{display:grid;grid-template-columns:140px 32px 140px 1fr;gap:8px;padding:8px 0;border-bottom:1px solid var(--line)}
.symbol{display:grid;grid-template-columns:50px 120px 1fr 1fr;gap:9px;padding:7px;border-bottom:1px solid var(--line)}.muted{color:var(--muted)}h2{font-size:16px;margin:5px 0 12px}h3{font-size:14px;margin:18px 0 8px}
</style>
</head>
<body>
<header><div class="brand">Glyph Studio</div><div id="path" class="path"></div><div id="status" class="status">starting</div><button id="rebuild">Rebuild</button><button id="save" class="primary">Save</button></header>
<main><section class="editor-pane"><div class="pane-title">Source</div><textarea id="editor" spellcheck="false"></textarea></section><section class="viewer"><nav id="tabs" class="tabs"></nav><div id="content" class="content"></div></section></main>
<script>
const tabs=['Overview','Machine','Flow','Temporal','Rust','Host','AST','Symbols','Artifacts'];let active='Overview',state=null,dirty=false,lastVersion=-1;
const editor=document.getElementById('editor'),content=document.getElementById('content');editor.addEventListener('input',()=>dirty=true);
document.getElementById('save').onclick=async()=>{await post('/api/save',{source:editor.value});dirty=false;await refresh(true)};document.getElementById('rebuild').onclick=async()=>{await post('/api/rebuild',{});await refresh(true)};
function esc(x){return String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function post(url,body){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
async function artifact(name){const r=await fetch('/api/artifact?name='+encodeURIComponent(name));return (await r.json()).content||''}
function makeTabs(){document.getElementById('tabs').innerHTML=tabs.map(t=>`<button class="tab ${t===active?'active':''}" data-t="${t}">${t}</button>`).join('');document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{active=b.dataset.t;makeTabs();render()})}
function diagnostics(){return (state.diagnostics||[]).map(d=>`<div class="error">${esc(d.message)}</div>`).join('')}
function overview(){const ir=state.execution_ir||{},sem=state.semantic||{};return diagnostics()+`<div class="cards"><div class="card"><div class="value">${(sem.functions||[]).length}</div><div class="label">Functions</div></div><div class="card"><div class="value">${(ir.machines||[]).length}</div><div class="label">Machines</div></div><div class="card"><div class="value">${(ir.temporal||[]).length}</div><div class="label">Temporal constraints</div></div><div class="card"><div class="value">${(sem.symbols||[]).length}</div><div class="label">Symbols</div></div></div><h3>Build</h3><pre>Status: ${esc(state.status)}\nUpdated: ${esc(state.updated_at)}\nDigest: ${esc((state.digest||'').slice(0,16))}\nOutput: ${esc(state.output_dir)}</pre>`}
function machine(){const ms=(state.execution_ir?.machines||[]);if(!ms.length)return '<div class="muted">machine declaration is not present.</div>';return ms.map(m=>{const states=m.states||[];const boxes=states.map((s,i)=>`<div class="state ${s.name===m.initial_state?'initial':''} ${s.name===m.success_state?'success':''} ${s.name===m.failure_state?'failure':''}"><b>${esc(s.name)}</b><div class="muted">${s.name===m.initial_state?'initial ':''}${s.terminal||''}</div></div>${i<states.length-1?'<div class="arrow">→</div>':''}`).join('');const ts=(m.transitions||[]).map(t=>`<div class="transition"><b>${esc(t.source_state)}</b><span>→</span><b>${esc(t.target_state)}</b><span>${esc(t.condition)}</span></div>`).join('');return `<h2>${esc(m.name)}</h2><div class="machine">${boxes}</div><h3>Transitions</h3>${ts}`}).join('')}
function flow(){const ir=state.execution_ir||{};const nodes=ir.nodes||[],edges=ir.edges||[];return `<h2>Execution flow</h2><div class="cards">${nodes.map(n=>`<div class="card"><b>${esc(n.label)}</b><div class="muted">${esc(n.kind)} · L${n.source?.line||0}</div></div>`).join('')}</div><h3>Edges</h3>${edges.map(e=>`<div class="transition"><b>${esc(e.source_id)}</b><span>→</span><b>${esc(e.target_id)}</b><span>${esc(e.label||e.kind)}</span></div>`).join('')}`}
function temporal(){const xs=state.execution_ir?.temporal||[];return `<h2>Temporal constraints</h2>${xs.map(x=>`<div class="card" style="margin-bottom:9px"><b>${esc(x.name)}</b><pre>${esc(x.formula)}</pre><div class="muted">${esc(x.streaming_monitor)}</div></div>`).join('')||'<div class="muted">No temporal constraints.</div>'}`}
async function code(name){content.innerHTML='<div class="muted">loading…</div>';content.innerHTML='<pre>'+esc(await artifact(name))+'</pre>'}
function ast(){return '<pre>'+esc(JSON.stringify(state.semantic||{},null,2))+'</pre>'}
function symbols(){return `<div class="symbol muted"><span>ID</span><span>Kind</span><span>Name</span><span>Type</span></div>${(state.semantic?.symbols||[]).map(s=>`<div class="symbol"><span>${s.id}</span><span>${esc(s.kind)}</span><b>${esc(s.name)}</b><span>${esc(s.type||'')}</span></div>`).join('')}`}
function artifacts(){return `<h2>Generated automatically</h2>${(state.artifact_names||[]).map(n=>`<div class="card" style="margin-bottom:8px"><b>${esc(n)}</b><div class="muted">${esc(state.output_dir+'/'+n)}</div></div>`).join('')}`}
function render(){if(!state)return;document.getElementById('path').textContent=state.source_path;const st=document.getElementById('status');st.textContent=state.status;st.className='status '+state.status;if(active==='Overview')content.innerHTML=overview();else if(active==='Machine')content.innerHTML=machine();else if(active==='Flow')content.innerHTML=flow();else if(active==='Temporal')content.innerHTML=temporal();else if(active==='Rust')code('generated.rs');else if(active==='Host')code('host.generated.rs');else if(active==='AST')content.innerHTML=ast();else if(active==='Symbols')content.innerHTML=symbols();else content.innerHTML=artifacts()}
async function refresh(force=false){const r=await fetch('/api/state',{cache:'no-store'});const next=await r.json();if(force||next.version!==lastVersion){state=next;lastVersion=next.version;if(!dirty)editor.value=state.source||'';render()}}
makeTabs();refresh(true);setInterval(()=>refresh(false),600);
</script>
</body></html>'''


def run_studio(input_path: str | Path) -> int:
    return GlyphStudio(input_path).serve()
