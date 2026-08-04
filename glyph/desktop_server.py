from __future__ import annotations

import argparse
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import threading
from typing import Any
from urllib.parse import urlsplit
import webbrowser

from . import diagram_app
from .diagram_app import (
    GlyphDiagramApp,
    SaveConflictError,
    SaveWriteError,
    ViewBuilder,
)
from .io_state_views import build_io_state_views
from .readable_diagram_app import prepare_diagram_app


_COOKIE_NAME = "glyph_desktop_session"
_HEADER_NAME = "X-Glyph-Desktop-Token"


@dataclass
class DesktopServer:
    app: GlyphDiagramApp
    server: ThreadingHTTPServer
    token: str
    require_auth: bool = True

    @property
    def origin(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def launch_url(self) -> str:
        if self.require_auth:
            return f"{self.origin}/launch/{self.token}"
        return f"{self.origin}/"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.app.stop()


def _cookie_contains(raw_cookie: str, token: str) -> bool:
    expected = f"{_COOKIE_NAME}={token}"
    return any(part.strip() == expected for part in raw_cookie.split(";"))


def _authenticated_html(html: str, token: str) -> str:
    bootstrap = f"""<script>
(() => {{
  const token = {json.dumps(token)};
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, init = {{}}) => {{
    const target = new URL(typeof input === 'string' ? input : input.url, window.location.href);
    if (target.origin === window.location.origin && target.pathname.startsWith('/api/')) {{
      const headers = new Headers(init.headers || (typeof input === 'string' ? undefined : input.headers));
      headers.set('X-Glyph-Desktop-Token', token);
      init = {{...init, headers}};
    }}
    return nativeFetch(input, init);
  }};
}})();
</script>"""
    return html.replace("</head>", bootstrap + "\n</head>", 1)


def create_desktop_server(
    source_path: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    token: str | None = None,
    require_auth: bool = True,
    view_builder: ViewBuilder = build_io_state_views,
) -> DesktopServer:
    """Create the shared loopback Glyph Studio server.

    The Tauri sidecar uses ``require_auth=True``. The direct Python launcher uses
    ``require_auth=False`` because it opens the loopback URL in the user's normal
    browser. Both modes use the same compiler, prepared HTML, API handlers, and
    live-update implementation.
    """

    prepare_diagram_app()
    app = GlyphDiagramApp(source_path, view_builder=view_builder)
    app.rebuild()
    app.start_watching()
    session_token = token or secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        server_version = "GlyphDesktop/1"

        def log_message(self, format: str, *args: object) -> None:
            return

        def _security_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if require_auth:
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; "
                    "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                    "font-src 'self' data:; frame-ancestors tauri: http://tauri.localhost "
                    "http://127.0.0.1:*",
                )

        def _json(
            self,
            value: object,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._security_headers()
            self.end_headers()
            self.wfile.write(payload)

        def _authorized(self) -> bool:
            if not require_auth:
                return True
            return (
                self.headers.get(_HEADER_NAME, "") == session_token
                or _cookie_contains(self.headers.get("Cookie", ""), session_token)
            )

        def _require_auth(self) -> bool:
            if self._authorized():
                return True
            self._json({"error": "desktop session required"}, HTTPStatus.FORBIDDEN)
            return False

        def _body(self) -> dict[str, Any] | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                body: Any = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                body = None
            if not isinstance(body, dict):
                self._json(
                    {"error": "request body must be an object"},
                    HTTPStatus.BAD_REQUEST,
                )
                return None
            return body

        def _serve_app(self) -> None:
            html = (
                _authenticated_html(diagram_app.DIAGRAM_HTML, session_token)
                if require_auth
                else diagram_app.DIAGRAM_HTML
            )
            payload = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            if require_auth:
                self.send_header(
                    "Set-Cookie",
                    f"{_COOKIE_NAME}={session_token}; HttpOnly; SameSite=Strict; Path=/",
                )
            self._security_headers()
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == f"/launch/{session_token}" or (
                not require_auth and path == "/"
            ):
                self._serve_app()
                return
            if path == "/api/state":
                if self._require_auth():
                    self._json(app.state_dict())
                return
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if not self._require_auth():
                return
            path = urlsplit(self.path).path
            if path == "/api/save":
                body = self._body()
                if body is None:
                    return
                source = body.get("source")
                base_digest = body.get("base_digest")
                if not isinstance(source, str):
                    self._json(
                        {"error": "source must be text"},
                        HTTPStatus.BAD_REQUEST,
                    )
                    return
                if base_digest is not None and not isinstance(base_digest, str):
                    self._json(
                        {"error": "base_digest must be text"},
                        HTTPStatus.BAD_REQUEST,
                    )
                    return
                try:
                    app.save_source_async(source, base_digest=base_digest)
                except SaveConflictError as exc:
                    self._json(
                        {
                            "error": "save_conflict",
                            "message": str(exc),
                            "current_source": exc.current_source,
                            "current_digest": exc.current_digest,
                            "state": app.state_dict(),
                        },
                        HTTPStatus.CONFLICT,
                    )
                    return
                except SaveWriteError as exc:
                    self._json(
                        {"error": exc.code, "message": str(exc)},
                        exc.status,
                    )
                    return
                self._json(app.state_dict(), HTTPStatus.ACCEPTED)
                return
            if path == "/api/rebuild":
                try:
                    app.rebuild_async()
                except SaveWriteError as exc:
                    self._json(
                        {"error": exc.code, "message": str(exc)},
                        exc.status,
                    )
                    return
                self._json(app.state_dict(), HTTPStatus.ACCEPTED)
                return
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    server = ThreadingHTTPServer((host, port), Handler)
    return DesktopServer(
        app=app,
        server=server,
        token=session_token,
        require_auth=require_auth,
    )


def run_studio_app(
    source_path: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    open_browser: bool | None = None,
    view_builder: ViewBuilder = build_io_state_views,
) -> int:
    """Run the current Studio UI directly in the user's local browser."""

    selected_port = (
        int(os.environ.get("GLYPH_DIAGRAM_PORT", "0")) if port is None else port
    )
    studio = create_desktop_server(
        source_path,
        host=host,
        port=selected_port,
        require_auth=False,
        view_builder=view_builder,
    )
    should_open = (
        os.environ.get("GLYPH_DIAGRAM_NO_BROWSER") != "1"
        if open_browser is None
        else open_browser
    )
    print(f"Glyph Studio: {studio.launch_url}")
    print(f"Source: {studio.app.input_path}")
    print("終了: Ctrl+C")
    if should_open:
        threading.Timer(0.15, lambda: webbrowser.open(studio.launch_url)).start()
    try:
        studio.server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        studio.server.server_close()
        studio.app.stop()
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Glyph desktop sidecar server")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    desktop = create_desktop_server(args.source, host=args.host, port=args.port)
    stopping = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        if stopping.is_set():
            return
        stopping.set()
        threading.Thread(target=desktop.server.shutdown, daemon=True).start()

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, stop)

    print(f"GLYPH_DESKTOP_READY={desktop.launch_url}", flush=True)
    try:
        desktop.server.serve_forever(poll_interval=0.2)
    finally:
        desktop.server.server_close()
        desktop.app.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
