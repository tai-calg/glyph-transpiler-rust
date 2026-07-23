from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .compiler import GlyphError
from .ui import UiProjectError, open_ui
from .ui_backends import UiBackendError, default_backend_registry
from .ui_ir import UiIrError
from .ui_schema import UiSchemaError


def _backend_option(text: str) -> tuple[str, Any]:
    if "=" not in text:
        raise argparse.ArgumentTypeError("backend option must use KEY=VALUE")
    key, raw_value = text.split("=", 1)
    key = key.strip()
    if not key:
        raise argparse.ArgumentTypeError("backend option key must not be empty")
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        value = raw_value
    return key, value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glyph-ui",
        description="Compile a pure Glyph function into backend-neutral UI IR and render it",
    )
    parser.add_argument("source", nargs="?", type=Path, help="Glyph source file")
    parser.add_argument(
        "--function",
        help="Pure function to expose. Defaults to render, main, or the sole candidate.",
    )
    parser.add_argument("--title", help="Application title")
    parser.add_argument("--backend", default="gradio", help="Registered UI backend")
    parser.add_argument(
        "--backend-option",
        action="append",
        default=[],
        type=_backend_option,
        metavar="KEY=VALUE",
        help="Backend-specific option. JSON values are decoded when possible.",
    )
    parser.add_argument(
        "--list-backends",
        action="store_true",
        help="List registered and discovered UI backends",
    )
    parser.add_argument(
        "--ui-ir-output",
        type=Path,
        help="Write glyph.ui-ir JSON to this path",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compile and print UI IR without loading a rendering backend",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Gradio server host")
    parser.add_argument("--port", type=int, default=7860, help="Gradio server port")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--share", action="store_true")
    parser.add_argument("--no-watch", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    registry = default_backend_registry()

    if args.list_backends:
        for name in registry.names():
            print(name)
        if args.source is None:
            return 0

    if args.source is None:
        parser.error("source is required unless --list-backends is used")

    backend_options = dict(args.backend_option)
    if args.backend == "gradio":
        backend_options.setdefault("server_name", args.host)
        backend_options.setdefault("server_port", args.port)
        backend_options.setdefault("inbrowser", not args.no_browser)
        backend_options.setdefault("share", args.share)
        backend_options.setdefault("watch", not args.no_watch)

    try:
        with open_ui(
            args.source,
            function_name=args.function,
            title=args.title,
            registry=registry,
        ) as project:
            if args.ui_ir_output is not None:
                args.ui_ir_output.parent.mkdir(parents=True, exist_ok=True)
                args.ui_ir_output.write_text(project.ui_ir_json(), encoding="utf-8")
            if args.check:
                sys.stdout.write(project.ui_ir_json())
                return 0
            project.launch(args.backend, **backend_options)
            return 0
    except (
        GlyphError,
        OSError,
        UiBackendError,
        UiIrError,
        UiProjectError,
        UiSchemaError,
        ValueError,
    ) as exc:
        print(f"glyph-ui: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
