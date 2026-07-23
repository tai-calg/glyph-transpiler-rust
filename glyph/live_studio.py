from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .live_image import LiveImage
from .live_studio_ui import LIVE_STUDIO_HTML
from .studio import GlyphStudio, StudioSnapshot


class LiveGlyphStudio(GlyphStudio):
    """Glyph Studio with a versioned transactional Live Image."""

    def __init__(self, input_path: str | Path):
        super().__init__(input_path)
        self.live_image = LiveImage()

    def rebuild(self, source: str | None = None) -> StudioSnapshot:
        snapshot = super().rebuild(source)
        if snapshot.status == "ready":
            generated = snapshot.artifacts.get("generated.rs", "")
            self.live_image.stage(
                snapshot.semantic,
                source_digest=snapshot.digest,
                generated_code=generated,
            )
        return snapshot

    def state_dict(self) -> dict[str, object]:
        state = super().state_dict()
        state["live_image"] = self.live_image.to_dict()
        names = state.get("artifact_names")
        if isinstance(names, list) and "live-image.json" not in names:
            names.append("live-image.json")
            names.sort()
        return state

    def artifact(self, name: str) -> str | None:
        if name == "live-image.json":
            return json.dumps(
                self.live_image.to_dict(),
                ensure_ascii=False,
                indent=2,
            ) + "\n"
        return super().artifact(name)

    def commit_live_patch(
        self,
        *,
        migration_plan: str | None = None,
        reader_acknowledged: bool = False,
    ) -> dict[str, object]:
        self.live_image.commit_pending(
            migration_plan=migration_plan,
            reader_acknowledged=reader_acknowledged,
        )
        return self.state_dict()

    def discard_live_patch(self) -> dict[str, object]:
        self.live_image.discard_pending()
        return self.state_dict()

    def create_server(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> ThreadingHTTPServer:
        studio = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "GlyphLiveStudio/1"

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

            def _source_from_body(self) -> str | None:
                source = self._body().get("source")
                if not isinstance(source, str):
                    self._json(
                        {"error": "source must be text"},
                        HTTPStatus.BAD_REQUEST,
                    )
                    return None
                return source

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/":
                    payload = LIVE_STUDIO_HTML.encode("utf-8")
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
                if parsed.path == "/api/live/state":
                    self._json(studio.live_image.to_dict())
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
                if self.path == "/api/preview":
                    source = self._source_from_body()
                    if source is None:
                        return
                    studio.preview_source(source)
                    self._json(studio.state_dict())
                    return
                if self.path == "/api/save":
                    source = self._source_from_body()
                    if source is None:
                        return
                    studio.save_source(source)
                    self._json(studio.state_dict())
                    return
                if self.path == "/api/rebuild":
                    studio.rebuild()
                    self._json(studio.state_dict())
                    return
                if self.path == "/api/live/discard":
                    self._body()
                    self._json(studio.discard_live_patch())
                    return
                if self.path == "/api/live/commit":
                    body = self._body()
                    migration_plan = body.get("migration_plan")
                    reader_acknowledged = body.get("reader_acknowledged", False)
                    if migration_plan is not None and not isinstance(migration_plan, str):
                        self._json(
                            {"error": "migration_plan must be text"},
                            HTTPStatus.BAD_REQUEST,
                        )
                        return
                    if not isinstance(reader_acknowledged, bool):
                        self._json(
                            {"error": "reader_acknowledged must be boolean"},
                            HTTPStatus.BAD_REQUEST,
                        )
                        return
                    try:
                        state = studio.commit_live_patch(
                            migration_plan=migration_plan,
                            reader_acknowledged=reader_acknowledged,
                        )
                    except RuntimeError as exc:
                        self._json(
                            {"error": str(exc)},
                            HTTPStatus.CONFLICT,
                        )
                        return
                    self._json(state)
                    return
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        return ThreadingHTTPServer((host, port), Handler)


def run_live_studio(input_path: str | Path) -> int:
    return LiveGlyphStudio(input_path).serve()
