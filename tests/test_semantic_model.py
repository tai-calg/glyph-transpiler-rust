from __future__ import annotations

import unittest

from glyph import parse_compilation_model


class SemanticModelTests(unittest.TestCase):
    def test_symbol_ids_are_deterministic(self) -> None:
        source = """
+Mode=Idle|Running
*S(mode:Mode,n:U)
>inc(x:U):U=x+1
>step(s:S):S=S(Running,inc(s.n))
"""
        first = parse_compilation_model(source).semantic.to_dict()
        second = parse_compilation_model(source).semantic.to_dict()
        self.assertEqual(first, second)
        names = {item["name"]: item["id"] for item in first["symbols"]}
        self.assertIn("step", names)
        self.assertIn("Running", names)

    def test_guard_function_is_one_expression_tree(self) -> None:
        source = """
>abs(x:I):I
  x<0 >> -x
  _ >> x
"""
        function = parse_compilation_model(source).semantic.function("abs")
        assert function is not None
        self.assertEqual(function.body.kind, "guard")
        self.assertEqual(len(function.body.children), 2)

    def test_nonstructural_recursion_is_allowed_and_unchecked(self) -> None:
        source = ">loop(x:U):U=loop(x)\n"
        function = parse_compilation_model(source).semantic.function("loop")
        assert function is not None
        self.assertTrue(function.recursion.recursive)
        self.assertEqual(function.recursion.analysis, "unchecked")

    def test_decreasing_self_recursion_is_marked_structural(self) -> None:
        source = """
>sum(n:U):U
  n==0 >> 0
  _ >> n+sum(n-1)
"""
        function = parse_compilation_model(source).semantic.function("sum")
        assert function is not None
        self.assertEqual(function.recursion.analysis, "structural")


if __name__ == "__main__":
    unittest.main()
