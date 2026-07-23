from __future__ import annotations

import unittest
from pathlib import Path

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views
from glyph.transition_semantics import enrich_io_state_views


ROOT = Path(__file__).resolve().parents[1]


def compile_semantic(path: Path) -> dict[str, object]:
    source = path.read_text(encoding="utf-8")
    output = CompilationPipeline().compile_text(source, source_name=str(path))
    views = build_io_state_views(output.model, output.diagrams.ir)
    return enrich_io_state_views(output.model, views)


def transition(machine: dict[str, object], source: str, target: str, event: str | None = None):
    matches = [
        item
        for item in machine["transitions"]
        if item["source_state"] == source
        and item["target_state"] == target
        and (event is None or item.get("event") == event)
    ]
    if not matches:
        raise AssertionError(f"missing transition {source} -> {target} event={event}")
    return matches[0]


class TransitionSemanticsTests(unittest.TestCase):
    def test_sum_variant_input_becomes_event_and_selector_is_not_repeated(self) -> None:
        views = compile_semantic(ROOT / "examples/state_diagrams/session_protocol.glyph")
        machine = views["state"]["machines"][0]

        start = transition(machine, "SessionIdle", "SessionConnecting", "SessionStart")
        self.assertEqual(start["display_label"], "SessionStart")
        self.assertIsNone(start["guard"])
        self.assertIsNone(start["action"])
        self.assertEqual(start["outcome"], "normal")

        rejected = transition(
            machine,
            "SessionConnecting",
            "SessionFailed",
            "SessionReject",
        )
        self.assertEqual(rejected["display_label"], "SessionReject")
        self.assertEqual(rejected["outcome"], "failure")
        self.assertFalse(rejected["synthesized_failure"])

    def test_non_event_boolean_condition_is_rendered_only_as_guard(self) -> None:
        views = compile_semantic(ROOT / "examples/state_diagrams/traffic_light.glyph")
        machine = views["state"]["machines"][0]

        cycle = transition(machine, "Red", "Green")
        self.assertIsNone(cycle["event"])
        self.assertEqual(cycle["guard"], "input.tick")
        self.assertEqual(cycle["display_label"], "[input.tick]")

        fault = transition(machine, "Red", "TrafficFault")
        self.assertIsNone(fault["event"])
        self.assertEqual(fault["guard"], "input.fault")
        self.assertEqual(fault["display_label"], "[input.fault]")
        self.assertEqual(fault["outcome"], "failure")

    def test_result_typed_effect_synthesizes_failure_transition(self) -> None:
        views = compile_semantic(ROOT / "examples/state_diagrams/effect_failure.glyph")
        machine = views["state"]["machines"][0]

        normal = transition(machine, "PumpOff", "PumpOn", "PumpStart")
        self.assertEqual(normal["action"], "write_pump(true)")
        self.assertEqual(normal["display_label"], "PumpStart / write_pump(true)")
        self.assertEqual(normal["outcome"], "normal")

        failures = [
            item
            for item in machine["transitions"]
            if item["source_state"] == "PumpOff"
            and item["target_state"] == "PumpFault"
            and item.get("event") == "PumpStart"
            and item.get("synthesized_failure")
        ]
        self.assertEqual(len(failures), 1)
        failure = failures[0]
        self.assertEqual(failure["failure_type"], "WriteError")
        self.assertEqual(failure["outcome"], "failure")
        self.assertEqual(
            failure["display_label"],
            "PumpStart / write_pump(true) ! WriteError",
        )
        self.assertNotIn("PumpFault", machine["unreachable_states"])
        self.assertGreaterEqual(
            machine["analysis"]["synthesized_failure_transition_count"],
            1,
        )

    def test_effect_without_result_does_not_create_failure_edge(self) -> None:
        source = """\
machine Device(state:DeviceState,event:DeviceEvent)
  select=state.mode
  init=DeviceState(DeviceOff,Ack(false))
  next=device_step(state,event)
  success=DeviceOff
  failure=DeviceFault

+DeviceEvent=DeviceStart|DeviceStop
+DeviceMode=DeviceOff|DeviceOn|DeviceFault
+DeviceAck=Ack(B)
*DeviceState(mode:DeviceMode,ack:DeviceAck)

!write_device(enabled:B):DeviceAck

>device_step(state:DeviceState,event:DeviceEvent):DeviceState
  event==DeviceStart >> DeviceState(DeviceOn,write_device(true))
  event==DeviceStop >> DeviceState(DeviceOff,write_device(false))
  _ >> state
"""
        output = CompilationPipeline().compile_text(source, source_name="device.glyph")
        views = enrich_io_state_views(
            output.model,
            build_io_state_views(output.model, output.diagrams.ir),
        )
        machine = views["state"]["machines"][0]
        self.assertEqual(
            machine["analysis"]["synthesized_failure_transition_count"],
            0,
        )
        self.assertFalse(
            any(item.get("synthesized_failure") for item in machine["transitions"])
        )


if __name__ == "__main__":
    unittest.main()
