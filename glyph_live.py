#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os

from glyph.live_studio import run_live_studio


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Glyph Studio with the transactional Live Image enabled."
    )
    parser.add_argument("input", help="Glyph source file")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the browser automatically",
    )
    args = parser.parse_args()
    if args.no_browser:
        os.environ["GLYPH_STUDIO_NO_BROWSER"] = "1"
    return run_live_studio(args.input)


if __name__ == "__main__":
    raise SystemExit(main())
