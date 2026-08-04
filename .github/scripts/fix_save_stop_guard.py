from pathlib import Path

path = Path("glyph/diagram_app.py")
text = path.read_text()
old = """            with self._save_lock:
                source_digest, _written = self._persist_source(
"""
new = """            with self._save_lock:
                with self._lock:
                    if self._stopping or self._stop.is_set():
                        raise SaveWriteError(
                            "server_stopping",
                            "Glyph Studio is stopping",
                            HTTPStatus.SERVICE_UNAVAILABLE,
                        )
                source_digest, _written = self._persist_source(
"""
if old not in text:
    raise SystemExit("missing anchor: pre-persist stopping guard")
path.write_text(text.replace(old, new, 1))
