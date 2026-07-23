from __future__ import annotations

from pathlib import Path
import unittest

try:
    import gradio  # noqa: F401
except ModuleNotFoundError:
    gradio = None

from glyph.pure_runtime import LivePureGlyphRuntime
from glyph.ui_ir import UiNode, build_ui_application

if gradio is not None:
    from glyph.gradio_renderer import (
        InputBinding,
        build_gradio_app,
        invoke_action,
    )


ROOT = Path(__file__).resolve().parents[1]


def leaf_nodes(node: UiNode) -> list[UiNode]:
    if node.kind == "object":
        leaves: list[UiNode] = []
        for child in node.children:
            leaves.extend(leaf_nodes(child))
        return leaves
    return [node]


def build_runtime_and_app(example: str):
    path = ROOT / "examples" / example
    runtime = LivePureGlyphRuntime(path)
    snapshot = runtime.compiler.last_snapshot
    if snapshot is None:
        runtime.stop()
        raise RuntimeError("compiler produced no snapshot")
    app = build_ui_application(snapshot.model, source_name=str(path))
    return runtime, app


@unittest.skipIf(gradio is None, "optional Gradio dependency is not installed")
class GenericGradioRendererTests(unittest.TestCase):
    def test_builds_component_graph_for_three_unrelated_apps(self) -> None:
        for example in (
            "gradio_temperature.glyph",
            "gradio_profile.glyph",
            "gradio_motor.glyph",
        ):
            with self.subTest(example=example):
                runtime, app = build_runtime_and_app(example)
                try:
                    demo = build_gradio_app(runtime, app)
                    self.assertIsNotNone(demo)
                finally:
                    runtime.stop()

    def test_profile_form_reconstructs_nested_product_and_invokes_glyph(self) -> None:
        runtime, app = build_runtime_and_app("gradio_profile.glyph")
        try:
            nodes = leaf_nodes(app.action.inputs[0])
            bindings = [InputBinding(node, None) for node in nodes]
            _, payload, history, session, _, _ = invoke_action(
                runtime,
                app,
                bindings,
                ["Ada", 35, True],
                {},
            )
        finally:
            runtime.stop()

        self.assertEqual(payload["name"], "Ada")
        self.assertTrue(payload["adult"])
        self.assertEqual(payload["access"]["variant"], "Admin")
        self.assertEqual(session["count"], 1)
        self.assertEqual(len(history), 1)

    def test_motor_form_is_not_bound_to_temperature_field_names(self) -> None:
        runtime, app = build_runtime_and_app("gradio_motor.glyph")
        try:
            nodes = leaf_nodes(app.action.inputs[0])
            bindings = [InputBinding(node, None) for node in nodes]
            _, payload, _, _, _, _ = invoke_action(
                runtime,
                app,
                bindings,
                [120.0, True, 80.0],
                {},
            )
        finally:
            runtime.stop()

        self.assertEqual(payload["command"], 80.0)
        self.assertEqual(payload["mode"]["variant"], "Limited")
        self.assertTrue(payload["safe"])


if __name__ == "__main__":
    unittest.main()
