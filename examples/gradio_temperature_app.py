from __future__ import annotations

from pathlib import Path
import sys


EXAMPLES_DIR = Path(__file__).resolve().parent
if str(EXAMPLES_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLES_DIR))

from gradio_temperature_dashboard import (  # noqa: E402,F401
    CSS,
    DEFAULT_SOURCE,
    LivePureGlyphRuntime,
    build_demo,
    main,
)


if __name__ == "__main__":
    main()
