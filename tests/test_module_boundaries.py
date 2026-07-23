from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _imports(relative: str) -> set[str]:
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"), filename=relative)
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
        elif isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
    return result


class ModuleBoundaryTests(unittest.TestCase):
    def test_host_requirement_ir_does_not_depend_on_builder_or_runtime_semantics(self) -> None:
        imports = _imports("glyph/host_requirements.py")

        self.assertNotIn("host_requirement_builder", imports)
        self.assertNotIn("contract_semantics", imports)

    def test_compilation_projection_uses_derived_facade(self) -> None:
        imports = _imports("glyph/compilation.py")

        self.assertIn("glyph04_derived", imports)
        self.assertNotIn("resource_flow", imports)
        self.assertNotIn("verification", imports)

    def test_type_normalizers_share_one_shortcut_definition(self) -> None:
        capability_imports = _imports("glyph/capability_type_normalize.py")
        contract_imports = _imports("glyph/contract_type_normalize.py")

        self.assertIn("type_shortcuts", capability_imports)
        self.assertIn("type_shortcuts", contract_imports)

    def test_artifact_layer_owns_rust_artifact_generation(self) -> None:
        artifacts = (ROOT / "glyph/artifacts.py").read_text(encoding="utf-8")
        compilation = (ROOT / "glyph/compilation.py").read_text(encoding="utf-8")

        self.assertIn("def build_rust_artifacts", artifacts)
        self.assertNotIn("def build_rust_artifacts", compilation)


if __name__ == "__main__":
    unittest.main()
