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
    self_same = enrich_runtime_io_state_views(output.model, views)
    assert self_same is views
    return views


def compile_source(source: str, name: str = "inline.glyph") -> dict[str, object]:
    output = CompilationPipeline().compile_text(source, source_name=name)
    return build_io_state_views(output.model, output.diagrams.ir)


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


def action_display(item: dict[str, object]) -> str:
    value = item.get("action")
    return str(value.get("display") or "") if isinstance(value, dict) else ""


def output_display(item: dict[str, object]) -> str:
    value = item.get("emitted_output")
    return str(value.get("display") or "") if isinstance(value, dict) else ""


class TransitionSemanticsTests(unittest.TestCase):
    def assert_v4(self, views: dict[str, object], machine: dict[str, object]) -> None:
        self.assertEqual(
            views["state_transition_ir"],
            {"schema": "glyph.state-transition-ir", "version": 4},
        )
        self.assertEqual(machine["transition_ir"]["version"], 4)
        self.assertEqual(machine["analysis"]["transition_ir_version"], 4)
        for index, item in enumerate(machine["transitions"], start=1):
            self.assertEqual(item["id"], f"T{index}")
            for field in (
                "source_state",
                "target_state",
                "trigger",
                "guards",
                "unclassified_conditions",
                "event",
                "guard",
                "action",
                "action_invocations",
                "emitted_output",
                "effect_invocations",
                "failure_type",
                "outcome",
                "source",
            ):
                self.assertIn(field, item)

    def test_sum_variant_input_becomes_confirmed_trigger(self) -> None:
        views = compile_semantic(ROOT / "examples/state_diagrams/session_protocol.glyph")
        machine = views["state"]["machines"][0]
        self.assert_v4(views, machine)

        start = transition(machine, "SessionIdle", "SessionConnecting", "SessionStart")
        self.assertEqual(start["display_label"], "SessionStart")
        self.assertIsNone(start["guard"])
        self.assertEqual(start["guards"], [])
        self.assertEqual(start["trigger"]["role"], "confirmed-trigger")
        self.assertEqual(start["trigger"]["confidence"], "exact")
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

    def test_boolean_input_is_warning_backed_provisional_trigger(self) -> None:
        views = compile_semantic(ROOT / "examples/state_diagrams/traffic_light.glyph")
        machine = views["state"]["machines"][0]

        cycle = transition(machine, "Red", "Green", "? input.tick")
        self.assertIsNone(cycle["guard"])
        self.assertEqual(cycle["guards"], [])
        self.assertEqual(cycle["display_label"], "? input.tick")
        self.assertEqual(cycle["trigger"]["role"], "provisional-trigger")

        fault = transition(machine, "Red", "TrafficFault", "? input.fault")
        self.assertIsNone(fault["guard"])
        self.assertEqual(fault["display_label"], "? input.fault")
        self.assertEqual(fault["outcome"], "failure")

        warning_codes = {item["code"] for item in machine["diagnostics"]}
        self.assertIn("STIR_TRIGGER_AMBIGUOUS_FALLBACK", warning_codes)

    def test_result_typed_effect_synthesizes_structured_failure_transition(self) -> None:
        views = compile_semantic(ROOT / "examples/state_diagrams/effect_failure.glyph")
        machine = views["state"]["machines"][0]

        normal = transition(machine, "PumpOff", "PumpOn", "PumpStart")
        self.assertEqual(action_display(normal), "write_pump(true)")
        self.assertEqual(
            normal["action"]["provenance"],
            "transition-operation-invocation",
        )
        self.assertEqual(
            [item["expression"] for item in normal["effect_invocations"]],
            ["write_pump(true)"],
        )
        self.assertIsNone(normal["failure_type"])
        self.assertEqual(normal["display_label"], "PumpStart")

        failures = [
            item
            for item in transitions(machine, "PumpOff", "PumpFault", "PumpStart")
            if item.get("synthesized_failure")
        ]
        self.assertEqual(len(failures), 1)
        failure = failures[0]
        self.assertEqual(action_display(failure), "write_pump(true)")
        self.assertEqual(
            [item["expression"] for item in failure["effect_invocations"]],
            ["write_pump(true)"],
        )
        self.assertEqual(failure["failure_type"], "WriteError")
        self.assertEqual(failure["outcome"], "failure")
        self.assertEqual(failure["display_label"], "PumpStart | WriteError")
        self.assertNotIn("PumpFault", machine["unreachable_states"])

    def test_event_guard_action_and_effect_are_all_preserved(self) -> None:
        views = compile_semantic(ROOT / "examples/state_diagrams/conveyor_control.glyph")
        machine = views["state"]["machines"][0]

        start = transition(
            machine,
            "ConveyorIdle",
            "ConveyorMoving",
            "ConveyorStart",
        )
        self.assertEqual(start["guard"], "input.clear")
        self.assertEqual(start["guards"], ["input.clear"])
        self.assertEqual(action_display(start), "set_conveyor(input.speed)")
        self.assertEqual(
            [item["expression"] for item in start["effect_invocations"]],
            ["set_conveyor(input.speed)"],
        )
        self.assertEqual(start["display_label"], "ConveyorStart [input.clear]")

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
        self.assertEqual(action_display(failure), "set_conveyor(input.speed)")
        self.assertEqual(
            [item["expression"] for item in failure["effect_invocations"]],
            ["set_conveyor(input.speed)"],
        )
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
        self.assertEqual(action_display(opened), "write_valve(true)")
        self.assertEqual(
            [item["expression"] for item in opened["effect_invocations"]],
            ["write_valve(true)"],
        )
        self.assertEqual(opened["display_label"], "ValveOpenRequest")
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
        self.assertEqual(action_display(failure), "write_valve(true)")
        self.assertEqual(
            [item["expression"] for item in failure["effect_invocations"]],
            ["write_valve(true)"],
        )
        self.assertEqual(failure["failure_type"], "ValveError")

        self.assertFalse(
            any(
                item["target_state"] == "ValveOpen"
                and item["source_state"] != item["target_state"]
                and item["event"] is None
                and item["expanded_from_wildcard"]
                for item in machine["transitions"]
            )
        )

    def test_distinct_boolean_inputs_remain_distinct_provisional_routes(self) -> None:
        views = compile_semantic(ROOT / "examples/state_diagrams/cooling_fan_effect.glyph")
        machine = views["state"]["machines"][0]
        failures = [
            item
            for item in machine["transitions"]
            if item.get("synthesized_failure")
            and any(
                effect.get("expression") == "write_fan(0.0)"
                for effect in item.get("effect_invocations", [])
            )
            and item.get("source_state") == "FanRunning"
        ]
        self.assertEqual(
            {item["event"] for item in failures},
            {"? input.overheat", "? !input.enable"},
        )
        self.assertTrue(all(item["guard"] is None for item in failures))
        self.assertTrue(all(item["failure_type"] == "FanWriteError" for item in failures))
        self.assertTrue(all(action_display(item) == "write_fan(0.0)" for item in failures))

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
        views = compile_source(source, "device.glyph")
        machine = views["state"]["machines"][0]
        self.assertEqual(
            machine["analysis"]["synthesized_failure_transition_count"],
            0,
        )
        self.assertFalse(
            any(item.get("synthesized_failure") for item in machine["transitions"])
        )
        actions = {
            action_display(item)
            for item in machine["transitions"]
            if action_display(item)
        }
        self.assertEqual(actions, {"write_device(true)", "write_device(false)"})

    def test_block_local_sum_value_is_inferred_from_input_dataflow(self) -> None:
        views = compile_semantic(ROOT / "examples/acceptance/door_controller.glyph")
        machine = views["state"]["machines"][0]
        alarm = next(
            item
            for item in machine["transitions"]
            if item["target_state"] == "Alarmed"
            and output_display(item) == "RaiseAlarm"
            and item.get("input_preimage")
        )
        self.assertEqual(alarm["trigger"]["role"], "inferred-trigger")
        self.assertEqual(alarm["trigger"]["confidence"], "dataflow-expanded")
        self.assertEqual(alarm["trigger"]["provenance"], "decision-output-preimage")
        self.assertIn("input.forced_open", alarm["trigger"]["display"])
        self.assertEqual(alarm["event"], alarm["trigger"]["display"])
        self.assertEqual(alarm["target_state"], "Alarmed")
        self.assertEqual(output_display(alarm), "RaiseAlarm")
        self.assertEqual(
            alarm["emitted_output"]["provenance"],
            "machine-output-projection",
        )
        self.assertEqual(
            action_display(alarm),
            "alarm(DoorState(Alarmed,state.failures+1,RaiseAlarm))",
        )
        self.assertEqual(
            [item["expression"] for item in alarm["effect_invocations"]],
            ["alarm(DoorState(Alarmed,state.failures+1,RaiseAlarm))"],
        )
        self.assertEqual(
            alarm["action_invocations"][0]["provenance"],
            "transition-result-consumer",
        )
        self.assertNotEqual(action_display(alarm), output_display(alarm))
        self.assertNotEqual(action_display(alarm), alarm["target_state"])
        self.assertNotIn("[action==RaiseAlarm]", alarm["display_label"])
        self.assertIn("input:input", alarm["trigger"]["provenance_roots"])

    def test_provisional_input_and_state_guard_are_separated(self) -> None:
        source = """\
machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Locked,0)
  next=step(state,input)
  success=Unlocked
  failure=Faulted

*Input(request_open:B)
+Mode=Locked|Unlocked|Faulted
*DoorState(mode:Mode,failures:U)

>step(state:DoorState,input:Input):DoorState
  state.mode==Locked&input.request_open&state.failures<3 >> DoorState(Unlocked,state.failures)
  _ >> state
"""
        views = compile_source(source, "provisional.glyph")
        machine = views["state"]["machines"][0]
        item = transition(machine, "Locked", "Unlocked", "? input.request_open")
        self.assertEqual(item["guards"], ["state.failures<3"])
        self.assertEqual(item["guard"], "state.failures<3")
        self.assertEqual(
            item["display_label"],
            "? input.request_open [state.failures<3]",
        )

    def test_confirmed_event_makes_remaining_boolean_input_a_guard(self) -> None:
        source = """\
machine Door(state:DoorState,input:Input)
  select=state.mode
  init=DoorState(Locked)
  next=step(state,input)
  success=Unlocked
  failure=Faulted

+DoorEvent=RequestOpen|ForcedOpen
*Input(event:DoorEvent,badge_valid:B)
+Mode=Locked|Unlocked|Faulted
*DoorState(mode:Mode)

>step(state:DoorState,input:Input):DoorState
  input.event==RequestOpen&input.badge_valid >> DoorState(Unlocked)
  _ >> state
"""
        views = compile_source(source, "confirmed.glyph")
        machine = views["state"]["machines"][0]
        item = transition(machine, "Locked", "Unlocked", "RequestOpen")
        self.assertEqual(item["trigger"]["role"], "confirmed-trigger")
        self.assertEqual(item["guards"], ["input.badge_valid"])
        self.assertEqual(item["display_label"], "RequestOpen [input.badge_valid]")


if __name__ == "__main__":
    unittest.main()
