from __future__ import annotations

import unittest
from pathlib import Path

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views
from glyph.transition_semantics_runtime import enrich_runtime_io_state_views


ROOT = Path(__file__).resolve().parents[1]


def compile_semantic(path: Path) -> dict[str, object]:
    source = path.read_text(encoding="utf-8")
    output = CompilationPipeline().compile_text(source, source_name=str(path))
    views = build_io_state_views(output.model, output.diagrams.ir)
    # Compatibility entry point must be idempotent for compiler-produced v2 views.
    self_same = enrich_runtime_io_state_views(output.model, views)
    assert self_same is views
    return views


def transitions(
    machine: dict[str, object],
    source: str,
    target: str,
    event: str | None = None,
) -> list[dict[str, object]]:
    return [
        item
        for item in machine["transitions"]
        if item["source_state"] == source
        and item["target_state"] == target
        and (event is None or item.get("event") == event)
    ]


def transition(
    machine: dict[str, object],
    source: str,
    target: str,
    event: str | None = None,
) -> dict[str, object]:
    matches = transitions(machine, source, target, event)
    if not matches:
        raise AssertionError(f"missing transition {source} -> {target} event={event}")
    return matches[0]


class TransitionSemanticsTests(unittest.TestCase):
    def assert_v2(self, views: dict[str, object], machine: dict[str, object]) -> None:
        self.assertEqual(
            views["state_transition_ir"],
            {"schema": "glyph.state-transition-ir", "version": 2},
        )
        self.assertEqual(machine["transition_ir"]["version"], 2)
        self.assertEqual(machine["analysis"]["transition_ir_version"], 2)
        for index, item in enumerate(machine["transitions"], start=1):
            self.assertEqual(item["id"], f"T{index}")
            for field in (
                "source_state",
                "target_state",
                "event",
                "guard",
                "action",
                "failure_type",
                "outcome",
                "source",
            ):
                self.assertIn(field, item)

    def test_sum_variant_input_becomes_event_and_selector_is_not_repeated(self) -> None:
        views = compile_semantic(ROOT / "examples/state_diagrams/session_protocol.glyph")
        machine = views["state"]["machines"][0]
        self.assert_v2(views, machine)

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

    def test_result_typed_effect_synthesizes_structured_failure_transition(self) -> None:
        views = compile_semantic(ROOT / "examples/state_diagrams/effect_failure.glyph")
        machine = views["state"]["machines"][0]

        normal = transition(machine, "PumpOff", "PumpOn", "PumpStart")
        self.assertEqual(normal["action"], "write_pump(true)")
        self.assertIsNone(normal["failure_type"])
        self.assertEqual(normal["display_label"], "PumpStart / write_pump(true)")

        failures = [
            item
            for item in transitions(machine, "PumpOff", "PumpFault", "PumpStart")
            if item.get("synthesized_failure")
        ]
        self.assertEqual(len(failures), 1)
        failure = failures[0]
        self.assertEqual(failure["action"], "write_pump(true)")
        self.assertEqual(failure["failure_type"], "WriteError")
        self.assertEqual(failure["outcome"], "failure")
        self.assertEqual(
            failure["display_label"],
            "PumpStart / write_pump(true) | WriteError",
        )
        self.assertNotIn("PumpFault", machine["unreachable_states"])

    def test_event_guard_and_action_are_all_preserved(self) -> None:
        views = compile_semantic(ROOT / "examples/state_diagrams/conveyor_control.glyph")
        machine = views["state"]["machines"][0]

        start = transition(
            machine,
            "ConveyorIdle",
            "ConveyorMoving",
            "ConveyorStart",
        )
        self.assertEqual(start["guard"], "input.clear")
        self.assertEqual(start["action"], "set_conveyor(input.speed)")
        self.assertEqual(
            start["display_label"],
            "ConveyorStart [input.clear] / set_conveyor(input.speed)",
        )

        failure = next(
            item
            for item in transitions(
                machine,
                "ConveyorIdle",
                "ConveyorFault",
                "ConveyorStart",
            )
            if item.get("synthesized_failure")
        )
        self.assertEqual(failure["guard"], "input.clear")
        self.assertEqual(failure["action"], "set_conveyor(input.speed)")
        self.assertEqual(failure["failure_type"], "DriveError")

    def test_nested_pure_helper_keeps_outer_event_and_has_no_helper_wildcards(self) -> None:
        views = compile_semantic(ROOT / "examples/state_diagrams/valve_nested_effect.glyph")
        machine = views["state"]["machines"][0]

        opened = transition(
            machine,
            "ValveClosed",
            "ValveOpen",
            "ValveOpenRequest",
        )
        self.assertEqual(opened["action"], "write_valve(true)")
        self.assertEqual(
            opened["display_label"],
            "ValveOpenRequest / write_valve(true)",
        )
        failure = next(
            item
            for item in transitions(
                machine,
                "ValveClosed",
                "ValveFault",
                "ValveOpenRequest",
            )
            if item.get("synthesized_failure")
        )
        self.assertEqual(failure["action"], "write_valve(true)")
        self.assertEqual(failure["failure_type"], "ValveError")

        # Unguarded helper declarations are implementation details, not independent
        # wildcard transitions from every state.
        self.assertFalse(
            any(
                item["target_state"] == "ValveOpen"
                and item["event"] is None
                and item["expanded_from_wildcard"]
                for item in machine["transitions"]
            )
        )

    def test_distinct_guards_are_distinct_failure_routes(self) -> None:
        views = compile_semantic(ROOT / "examples/state_diagrams/cooling_fan_effect.glyph")
        machine = views["state"]["machines"][0]
        failures = [
            item
            for item in machine["transitions"]
            if item.get("synthesized_failure")
            and item.get("action") == "write_fan(0.0)"
            and item.get("source_state") == "FanRunning"
        ]
        self.assertEqual(
            {item["guard"] for item in failures},
            {"input.overheat", "!input.enable"},
        )
        self.assertTrue(all(item["failure_type"] == "FanWriteError" for item in failures))

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
        views = build_io_state_views(output.model, output.diagrams.ir)
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
