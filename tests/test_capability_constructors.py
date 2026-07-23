from __future__ import annotations

import unittest

from glyph import compile_source, parse_compilation_model


class CapabilityConstructorTests(unittest.TestCase):
    def test_owned_resource_may_move_into_nested_error_constructor(self) -> None:
        source = (
            "resource Tx[Open]\n"
            "+E=Bad\n"
            "*RunError(tx:own Tx[Open],cause:E)\n"
            ">run(tx:own Tx[Open]):I|RunError=Err(RunError(tx,Bad))\n"
        )

        generated = compile_source(source)
        model = parse_compilation_model(source)

        self.assertIn("RunError", generated)
        moves = [
            item
            for item in model.capabilities.operations
            if item.function == "run" and item.kind == "move"
        ]
        self.assertEqual([item.source for item in moves], ["tx"])

    def test_owned_resource_may_move_into_sum_variant(self) -> None:
        source = (
            "resource Tx[Open]\n"
            "+E=Bad\n"
            "+Outcome=Failed(own Tx[Open],E)\n"
            ">run(tx:own Tx[Open]):Outcome=Failed(tx,Bad)\n"
        )

        model = parse_compilation_model(source)
        self.assertTrue(
            any(
                item.function == "run"
                and item.kind == "move"
                and item.source == "tx"
                for item in model.capabilities.operations
            )
        )


if __name__ == "__main__":
    unittest.main()
