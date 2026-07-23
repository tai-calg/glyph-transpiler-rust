from __future__ import annotations

import argparse
from pathlib import Path
import sys

from glyph.pure_runtime import LivePureGlyphRuntime
from glyph.ui_ir import UiIrError, build_ui_application


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a pure Glyph function as a generic Gradio application"
    )
    parser.add_argument("source", type=Path, help="Glyph source file")
    parser.add_argument(
        "--function",
        help="Pure Glyph function to expose. Defaults to render, main, or the sole candidate.",
    )
    parser.add_argument("--title", help="Application title")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--ui-ir-output",
        type=Path,
        help="Write glyph.ui-ir JSON to this path",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compile and print UI IR without importing Gradio or starting a server",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runtime = LivePureGlyphRuntime(args.source)
    try:
        snapshot = runtime.compiler.last_snapshot
        if snapshot is None:
            raise RuntimeError("compiler produced no snapshot")
        app = build_ui_application(
            snapshot.model,
            function_name=args.function,
            source_name=str(args.source),
            title=args.title,
        )
        if args.ui_ir_output is not None:
            args.ui_ir_output.parent.mkdir(parents=True, exist_ok=True)
            args.ui_ir_output.write_text(app.to_json(), encoding="utf-8")
        if args.check:
            sys.stdout.write(app.to_json())
            return 0

        from glyph.gradio_renderer import GENERIC_GRADIO_CSS, build_gradio_app
        import gradio as gr

        runtime.start_watching()
        demo = build_gradio_app(runtime, app)
        demo.launch(
            server_name=args.host,
            server_port=args.port,
            inbrowser=not args.no_browser,
            theme=gr.themes.Ocean(),
            css=GENERIC_GRADIO_CSS,
        )
        return 0
    except (UiIrError, OSError, RuntimeError, ValueError) as exc:
        print(f"glyph-gradio: {exc}", file=sys.stderr)
        return 1
    finally:
        runtime.stop()


if __name__ == "__main__":
    raise SystemExit(main())
