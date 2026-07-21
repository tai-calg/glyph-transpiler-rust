from __future__ import annotations

import json
import unittest

from tests.acceptance_support import EXAMPLES, SCHEMAS, compile_example, load


class AcceptanceSchemaTests(unittest.TestCase):
    def test_outputs_are_deterministic_and_versioned(self) -> None:
        for name in EXAMPLES:
            first = compile_example(name)
            second = compile_example(name)
            self.assertEqual(first.artifacts, second.artifacts, name)
            self.assertEqual(first.design_json, second.design_json, name)
            self.assertEqual(first.diagrams.files, second.diagrams.files, name)
            design = json.loads(first.design_json)
            self.assertEqual((design["schema"], design["version"]), ("glyph.typed-design", 1))
            for filename, schema in SCHEMAS.items():
                payload = load(first, filename)
                self.assertEqual((payload["schema"], payload["version"]), (schema, 1))

    def test_human_views_hide_lowering_helpers(self) -> None:
        for name in EXAMPLES:
            outputs = compile_example(name)
            self.assertNotIn("__glyph_", outputs.diagrams.files["logic.mmd"])
            self.assertNotIn("__glyph_", outputs.diagrams.files["algorithm-ir.json"])


if __name__ == "__main__":
    unittest.main()
