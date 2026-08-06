from __future__ import annotations

import os
from pathlib import Path
import sys
import time

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from glyph.desktop_server import run_studio_app
from glyph.io_state_views import build_io_state_views


def slow_view_builder(model: object, ir: object) -> dict[str, object]:
    views = build_io_state_views(model, ir)
    time.sleep(float(os.environ.get("GLYPH_UX_COMPILE_DELAY", "1.2")))
    return views


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: run_interactive_save_ux_server.py <source.glyph>")
    return run_studio_app(
        Path(sys.argv[1]),
        open_browser=False,
        view_builder=slow_view_builder,
    )


if __name__ == "__main__":
    raise SystemExit(main())
