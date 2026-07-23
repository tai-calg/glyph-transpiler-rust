from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from glyph import compile_outputs


ROOT = Path(__file__).resolve().parents[1]


class HostRequirementTests(unittest.TestCase):
    def test_complete_system_emits_all_semantic_host_axes(self) -> None:
        source = (ROOT / "examples" / "acceptance" / "glyph04_system.glyph").read_text(
            encoding="utf-8"
        )
        outputs = compile_outputs(source, "glyph04_system.glyph")
        payload = json.loads(outputs.diagrams.files["host-requirements-ir.json"])
        kinds = {item["kind"] for item in payload["operations"]}

        self.assertEqual(payload["schema"], "glyph.host-requirements")
        self.assertEqual(payload["version"], 1)
        self.assertIn("publish", kinds)
        self.assertIn("resource_transition", kinds)
        self.assertIn("world_scope", kinds)
        self.assertIn("protocol_send", kinds)
        self.assertIn("protocol_receive", kinds)
        self.assertIn("handler_timeout", kinds)
        self.assertIn("handler_retry", kinds)
        self.assertIn("handler_return_error", kinds)
        self.assertIn("law_observe", kinds)
        self.assertIn("host_requirements", json.loads(outputs.design_json))

    def test_representation_slots_are_world_specific(self) -> None:
        source = (
            "'@UiWorld = Ui * App/Window\n"
            "'@WorkerWorld = Worker * App/Task\n"
            "'UiUse = {'UiWorld}\n"
            "'WorkerUse = {'WorkerWorld}\n"
            ">ui(value:share Service):share Service=value @{'UiUse}\n"
            ">worker(value:share Service):share Service=value @{'WorkerUse}\n"
        )
        outputs = compile_outputs(source)
        payload = json.loads(outputs.diagrams.files["host-requirements-ir.json"])
        service_slots = [
            item
            for item in payload["representations"]
            if item["type"]["name"] == "Service"
            and item["type"]["capability"] == "share"
        ]

        self.assertEqual({item["world"] for item in service_slots}, {"UiWorld", "WorkerWorld"})
        self.assertEqual(len({item["associated_type"] for item in service_slots}), 2)

    def test_generated_binding_is_representation_neutral_and_compiles(self) -> None:
        source = (ROOT / "examples" / "acceptance" / "glyph04_system.glyph").read_text(
            encoding="utf-8"
        )
        generated = compile_outputs(source).diagrams.files["host-binding.generated.rs"]

        for forbidden in ("Rc<", "Arc<", "Weak<", "Mutex<", "tokio::", "cuda"):
            self.assertNotIn(forbidden, generated)
        self.assertIn("pub trait GlyphHostBinding", generated)
        self.assertIn("type Repr", generated)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "host_binding.rs"
            path.write_text(generated, encoding="utf-8")
            subprocess.run(
                ["rustc", "--edition", "2021", "--crate-type", "lib", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )

    def test_plain_source_emits_no_host_binding_artifacts(self) -> None:
        outputs = compile_outputs(">double(x:I):I=x*2\n")
        design = json.loads(outputs.design_json)

        self.assertNotIn("host_requirements", design)
        self.assertNotIn("host-requirements-ir.json", outputs.diagrams.files)
        self.assertNotIn("host-binding.generated.rs", outputs.diagrams.files)


if __name__ == "__main__":
    unittest.main()
