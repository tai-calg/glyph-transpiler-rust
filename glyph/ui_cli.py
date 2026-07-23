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
from .ui_manifest import UiManifestError
from .ui_public import open_ui_project
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
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional glyph.ui-manifest v1 presentation metadata",
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
    parser.add_argument("--watch-interval", type=float, default=0.35)
    return parser


def _write_ui_ir(text: str, output: Path | None) -> None:
    if output is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def _run_manifest_compat(args: argparse.Namespace) -> int:
    if args.backend != "gradio":
        raise ValueError("--manifest currently supports only the gradio backend")
    if args.backend_option:
        raise ValueError("--backend-option cannot be combined with --manifest")

    with open_ui_project(
        args.source,
        function=args.function,
        title=args.title,
        manifest=args.manifest,
    ) as project:
        ui_ir = project.ui_ir_json()
        _write_ui_ir(ui_ir, args.ui_ir_output)
        if args.check:
            sys.stdout.write(ui_ir)
            return 0

        try:
            import gradio as gr
            from .gradio_renderer import GENERIC_GRADIO_CSS
        except ModuleNotFoundError as exc:
            if exc.name in {"gradio", "pandas"}:
                raise RuntimeError(
                    "UI dependencies are missing; install glyph-rust[ui]"
                ) from exc
            raise

        if not args.no_watch:
            project.start_watching(args.watch_interval)
        demo = project.render("gradio")
        demo.launch(
            server_name=args.host,
            server_port=args.port,
            inbrowser=not args.no_browser,
            share=args.share,
            theme=gr.themes.Ocean(),
            css=GENERIC_GRADIO_CSS,
        )
        return 0


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
    if args.port < 1 or args.port > 65535:
        parser.error("--port must be in [1, 65535]")
    if args.watch_interval < 0.1:
        parser.error("--watch-interval must be at least 0.1")

    try:
        if args.manifest is not None:
            return _run_manifest_compat(args)

        backend_options = dict(args.backend_option)
        if args.backend == "gradio":
            backend_options.setdefault("server_name", args.host)
            backend_options.setdefault("server_port", args.port)
            backend_options.setdefault("inbrowser", not args.no_browser)
            backend_options.setdefault("share", args.share)
            backend_options.setdefault("watch", not args.no_watch)
            backend_options.setdefault("watch_interval", args.watch_interval)

        with open_ui(
            args.source,
            function_name=args.function,
            title=args.title,
            registry=registry,
        ) as project:
            ui_ir = project.ui_ir_json()
            _write_ui_ir(ui_ir, args.ui_ir_output)
            if args.check:
                sys.stdout.write(ui_ir)
                return 0
            project.launch(args.backend, **backend_options)
            return 0
    except (
        GlyphError,
        OSError,
        RuntimeError,
        UiBackendError,
        UiIrError,
        UiManifestError,
        UiProjectError,
        UiSchemaError,
        ValueError,
    ) as exc:
        print(f"glyph-ui: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
