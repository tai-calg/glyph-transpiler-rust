from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

from glyph import compile_artifact_files


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("cargo"), "cargoがない環境ではRust側テストを省略")
class RustDemoTests(unittest.TestCase):
    def test_demo_compiles_and_passes(self) -> None:
        compile_artifact_files(
            ROOT / "examples" / "controller.glyph",
            ROOT / "demo" / "src" / "generated.rs",
            ROOT / "demo" / "src" / "host.generated.rs",
        )
        subprocess.run(
            ["cargo", "test", "--manifest-path", str(ROOT / "demo" / "Cargo.toml")],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
