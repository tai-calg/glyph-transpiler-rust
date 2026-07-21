from __future__ import annotations

import unittest

from tests.acceptance_support import EXAMPLES, compile_example, load


class AcceptanceOrderTests(unittest.TestCase):
    def test_algorithm_binding_order_matches_generated_rust(self) -> None:
        for name in EXAMPLES:
            outputs = compile_example(name)
            algorithm = load(outputs, "algorithm-ir.json")
            rust = outputs.artifacts.logic
            for function in algorithm["functions"]:
                start = rust.index(f"pub fn {function['name']}")
                end = rust.find("\npub fn ", start + 1)
                body = rust[start:] if end < 0 else rust[start:end]
                positions = []
                for step in function["steps"]:
                    if step["kind"] != "binding":
                        continue
                    position = body.find(f"let {step['name']} =")
                    self.assertGreaterEqual(position, 0, (name, function["name"], step["name"]))
                    positions.append(position)
                self.assertEqual(positions, sorted(positions), (name, function["name"]))


if __name__ == "__main__":
    unittest.main()
