from __future__ import annotations

import unittest

from glyph import compile_source, parse_compilation_model


class ContractLawBridgeTests(unittest.TestCase):
    def test_product_law_generates_existing_temporal_monitor(self) -> None:
        source = (
            "'?Safe = @A(!fault >> stopped)\n"
            "'Observed = {'Safe}\n"
            "*Observation(fault:B,stopped:B) @{'Observed}\n"
        )

        model = parse_compilation_model(source)
        generated = compile_source(source)

        self.assertEqual(model.specs[0].name, "contract_Safe_Observation")
        self.assertIn("ContractSafeObservationMonitor", generated)
        self.assertIn("ContractSafeObservationStreamingMonitor", generated)

    def test_function_lifecycle_law_stays_runtime_contract_only(self) -> None:
        source = (
            "'?Deadline = @A(start >> @E 2s finish)\n"
            "'Use = {'Deadline}\n"
            ">run(x:I):I=x @{'Use}\n"
        )

        model = parse_compilation_model(source)

        self.assertEqual(model.specs, ())
        self.assertEqual(model.runtime_contracts.laws[0].verification, "model+runtime")


if __name__ == "__main__":
    unittest.main()
