from __future__ import annotations

import json
import unittest

from glyph import compile_outputs


class ResourceFlowTests(unittest.TestCase):
    def test_state_transition_preserves_symbolic_identity(self) -> None:
        outputs = compile_outputs(
            "resource Buffer[Ready|Used]\n"
            "!consume(buffer:own Buffer[Ready]):own Buffer[Used]\n"
        )
        payload = json.loads(outputs.diagrams.files["resource-flow-ir.json"])
        transition = payload["transitions"][0]

        self.assertEqual(transition["kind"], "transition")
        self.assertEqual(transition["source"]["identity"], transition["target"]["identity"])
        self.assertEqual(transition["source"]["state"], "Ready")
        self.assertEqual(transition["target"]["state"], "Used")

    def test_failure_and_success_paths_keep_same_resource_identity(self) -> None:
        outputs = compile_outputs(
            "resource Buffer[Ready|Used]\n"
            "+E=Bad\n"
            "*WriteError(buffer:own Buffer[Ready],cause:E)\n"
            "!write(buffer:own Buffer[Ready]):own Buffer[Used]|WriteError\n"
        )
        payload = json.loads(outputs.diagrams.files["resource-flow-ir.json"])
        identities = {
            transition["target"]["identity"]
            for transition in payload["transitions"]
            if transition["function"] == "write"
        }

        self.assertEqual(identities, {"rho:write:buffer"})

    def test_plain_source_does_not_emit_resource_flow_ir(self) -> None:
        outputs = compile_outputs(">double(x:I):I=x*2\n")
        self.assertNotIn("resource-flow-ir.json", outputs.diagrams.files)


if __name__ == "__main__":
    unittest.main()
