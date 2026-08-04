from __future__ import annotations

import os
from pathlib import Path
import sys
import time

from glyph.diagram_app import GlyphDiagramApp
from glyph.io_state_views import build_io_state_views


def slow_view_builder(model: object, ir: object) -> dict[str, object]:
    views = build_io_state_views(model, ir)
    time.sleep(float(os.environ.get("GLYPH_UX_COMPILE_DELAY", "1.2")))
    return views


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: run_interactive_save_ux_server.py <source.glyph>")
    app = GlyphDiagramApp(Path(sys.argv[1]), view_builder=slow_view_builder)
    return app.serve(open_browser=False)


if __name__ == "__main__":
    raise SystemExit(main())
