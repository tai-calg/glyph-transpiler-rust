from __future__ import annotations

import json
import unittest

from glyph import compile_diagram_bundle


SOURCE = """
+Mode=Idle|Running|Stopped|Faulted
+Command=Stop|Run(U)
+Error=Bad
*Input(tick,send,ack:B)
*System(mode:Mode,count:U,command:Command)

?ack(*Input)=@A(send>>@E 500ms ack)

>step(state:System,input:Input):System|Error
  state.mode==Idle >> Ok(System(Running,state.count+1,Run(1)))
  state.mode==Running >> Ok(System(Stopped,state.count+1,Stop))
  _ >> Ok(state)

machine Controller(state:System,input:Input)
  select=state.mode
  init=System(Idle,0,Stop)
  next=step(state,input)
  success=Stopped
  failure=Faulted
""".lstrip()


class ExecutionIRTests(unittest.TestCase):
    def test_ir_contains_dataflow_machine_and_temporal_views(self) -> None:
        bundle = compile_diagram_bundle(SOURCE, "controller.glyph")
        ir = bundle.ir

        self.assertIn("step", {node.label for node in ir.nodes})
        self.assertEqual(len(ir.machines), 1)
        machine = ir.machines[0]
        self.assertEqual(machine.initial_state, "Idle")
        self.assertEqual(machine.success_state, "Stopped")
        self.assertEqual(machine.failure_state, "Faulted")
        self.assertIn(
            ("Idle", "Running"),
            {(item.source_state, item.target_state) for item in machine.transitions},
        )
        self.assertIn(
            ("Running", "Stopped"),
            {(item.source_state, item.target_state) for item in machine.transitions},
        )
        self.assertEqual(ir.temporal[0].name, "ack")

    def test_mermaid_nodes_link_back_to_source_lines(self) -> None:
        bundle = compile_diagram_bundle(
            SOURCE,
            "controller.glyph",
            "../examples/controller.glyph",
        )
        execution = bundle.files["execution.mmd"]
        self.assertIn("click fn_step", execution)
        self.assertIn("../examples/controller.glyph#L", execution)

    def test_reverse_source_map_is_machine_readable(self) -> None:
        bundle = compile_diagram_bundle(SOURCE, "controller.glyph")
        source_map = json.loads(bundle.files["source-map.json"])
        self.assertEqual(source_map["source"], "controller.glyph")
        kinds = {
            item["kind"]
            for items in source_map["line_to_views"].values()
            for item in items
        }
        self.assertIn("execution-node", kinds)
        self.assertIn("machine-transition", kinds)
        self.assertIn("temporal", kinds)


if __name__ == "__main__":
    unittest.main()
