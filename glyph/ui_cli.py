from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .ui_manifest import UiManifestError
from .ui_public import open_ui_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glyph-gradio",
        description="Compile a pure Glyph function into a typed public UI application",
    )
    parser.add_argument("source", type=Path, help="Glyph source file")
    parser.add_argument("--function", help="Pure Glyph function to expose")
    parser.add_argument("--manifest", type=Path, help="glyph.ui-manifest JSON file")
    parser.add_argument("--title", help="Application title")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--watch-interval", type=float, default=0.35)
    parser.add_argument("--ui-ir-output", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compile and print glyph.ui-ir without importing Gradio",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.port < 1 or args.port > 65535:
        print("glyph-gradio: --port must be in [1, 65535]", file=sys.stderr)
        return 2
    if args.watch_interval < 0.1:
        print("glyph-gradio: --watch-interval must be at least 0.1", file=sys.stderr)
        return 2

    try:
        with open_ui_project(
            args.source,
            function=args.function,
            title=args.title,
            manifest=args.manifest,
        ) as project:
            if args.ui_ir_output is not None:
                args.ui_ir_output.parent.mkdir(parents=True, exist_ok=True)
                args.ui_ir_output.write_text(project.ui_ir_json(), encoding="utf-8")
            if args.check:
                sys.stdout.write(project.ui_ir_json())
                return 0

            try:
                import gradio as gr
                from .gradio_renderer import GENERIC_GRADIO_CSS
            except ModuleNotFoundError as exc:
                if exc.name in {"gradio", "pandas"}:
                    print(
                        "glyph-gradio: UI dependencies are missing; install glyph-rust[ui]",
                        file=sys.stderr,
                    )
                    return 2
                raise

            project.start_watching(args.watch_interval)
            demo = project.render("gradio")
            demo.launch(
                server_name=args.host,
                server_port=args.port,
                inbrowser=not args.no_browser,
                theme=gr.themes.Ocean(),
                css=GENERIC_GRADIO_CSS,
            )
            return 0
    except (OSError, RuntimeError, UiManifestError, ValueError) as exc:
        print(f"glyph-gradio: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
