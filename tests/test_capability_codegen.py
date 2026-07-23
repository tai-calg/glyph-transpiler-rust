from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
import unittest

from glyph import compile_source, parse_compilation_model


class CapabilityCodegenTests(unittest.TestCase):
    def test_shared_clone_lowers_to_rust_clone(self) -> None:
        source = (
            "*Service(id:I)\n"
            ">copy(shared:share Service):share Service=&shared as share\n"
        )
        generated = compile_source(source)

        self.assertIn("shared.clone()", generated)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "generated.rs"
            path.write_text(generated, encoding="utf-8")
            subprocess.run(
                ["rustc", "--edition", "2021", "--crate-type", "lib", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )

    def test_link_resolution_is_recorded_and_generates_valid_rust(self) -> None:
        source = (
            "*Service(id:I)\n"
            "+LinkExpired=Expired\n"
            ">resolve(weak:link Service):share Service|LinkExpired\n"
            "  live := (&weak as share)?\n"
            "  Ok(live)\n"
        )
        model = parse_compilation_model(source)
        generated = compile_source(source)

        self.assertTrue(
            any(
                item.function == "resolve"
                and item.kind == "capability_cast"
                and item.capability == "share"
                for item in model.capabilities.operations
            )
        )
        self.assertIn("weak.clone()", generated)
        self.assertNotIn("(weak)?", generated)


if __name__ == "__main__":
    unittest.main()
