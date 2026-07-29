from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Mapping

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views

GENERATED_PATH = ROOT / "build/state-diagram-regression/motor-safety-motor.png"
COMMITTED_PATH = ROOT / "docs/images/glyph-studio-state-transition.png"
MOTOR_SOURCE_PATH = ROOT / "examples/acceptance/motor_safety.glyph"
EXPECTED_SIZE = (1800, 1100)

# Independent Chromium runs can differ in a small anti-aliased edge band even
# when semantic roles, geometry, and line breaks are identical. These limits
# cover the measured raster-only envelope while remaining far below meaningful
# text or layout changes (which alter tens of thousands of pixels).
MAX_CHANGED_PIXELS = 1024
MAX_MEAN_ABSOLUTE_DELTA = 0.002
MAX_CHANNEL_DELTA = 48


def _enabling_cases(machine: Mapping[str, object]) -> list[Mapping[str, object]]:
    return [
        item
        for transition in machine.get("transitions", [])
        if isinstance(transition, Mapping)
        for item in transition.get("enabling_cases", [])
        if isinstance(item, Mapping)
    ]


def _display(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    return str(value.get("display") or value.get("expression") or "").strip()


def verify_readme_semantics() -> None:
    output = CompilationPipeline().compile_text(
        MOTOR_SOURCE_PATH.read_text(encoding="utf-8"),
        source_name=str(MOTOR_SOURCE_PATH),
    )
    views = build_io_state_views(output.model, output.diagrams.ir)
    machine = views["state"]["machines"][0]
    independence = machine["analysis"].get("action_target_independence", {})
    cases = _enabling_cases(machine)
    transitions = [
        item
        for item in machine.get("transitions", [])
        if isinstance(item, Mapping) and not item.get("synthesized_failure")
    ]

    failures: list[str] = []
    if independence.get("version") != 1:
        failures.append("generic Action/Target independence analysis is missing")
    if not independence.get("typed_independent"):
        failures.append(
            "Action occurrence type and Target State projection type are not distinct"
        )
    if not independence.get("behaviorally_independent"):
        failures.append(
            "the example has no behavioral witness that Action and Target State vary independently"
        )
    if int(independence.get("near_alias_count", 0)) != 0:
        failures.append(
            "Action names are lexical near-aliases of Target State names: "
            f"{independence.get('near_aliases', [])}"
        )
    if independence.get("mapping_shape") == "one-to-one":
        failures.append(
            "Action and Target State form a redundant one-to-one mapping"
        )

    if views.get("transition_operation_action_version") != 2:
        failures.append("operation-derived Action semantics v2 is missing")
    if machine.get("analysis", {}).get("state_field_action_count") != 0:
        failures.append("a state-field value is still classified as Action")

    operation_actions = []
    for transition in transitions:
        action = transition.get("action")
        if not isinstance(action, Mapping):
            continue
        operation_actions.append(action)
        action_display = _display(action)
        target_state = str(transition.get("target_state") or "")
        emitted_output = _display(transition.get("emitted_output"))
        if action.get("provenance") != "transition-operation-invocation":
            failures.append(
                f"Action `{action_display}` is not derived from an executed operation"
            )
        if not transition.get("action_invocations"):
            failures.append(
                f"Action `{action_display}` has no structured operation invocation witness"
            )
        if action_display and action_display == target_state:
            failures.append(
                f"Target State `{target_state}` leaked into Action"
            )
        if action_display and emitted_output and action_display == emitted_output:
            failures.append(
                f"Emitted Output `{emitted_output}` leaked into Action"
            )
    if not operation_actions:
        failures.append("the README example contains no executed transition Action")

    if views.get("transition_enabling_cases_version") != 1:
        failures.append("generic enabling-case analysis is missing")
    if not machine.get("analysis", {}).get("all_transitions_have_enabling_cases"):
        failures.append("not every rendered transition has an enabling case")

    priority_witnesses = []
    fallback_witnesses = []
    for item in cases:
        input_pattern = item.get("input_pattern")
        guard = item.get("guard")
        terms = guard.get("terms", []) if isinstance(guard, Mapping) else []
        origins = {
            str(term.get("origin") or "")
            for term in terms
            if isinstance(term, Mapping)
        }
        if isinstance(input_pattern, Mapping) and "priority-exclusion" in origins:
            input_expression = str(input_pattern.get("expression") or "")
            guard_expression = str(guard.get("expression") or "")
            if input_expression and guard_expression and guard_expression not in input_expression:
                priority_witnesses.append(item)
        if item.get("fallback") and input_pattern is None and "fallback" in origins:
            if isinstance(guard, Mapping) and guard.get("display") == "otherwise":
                fallback_witnesses.append(item)

    if not priority_witnesses:
        failures.append(
            "the README example does not prove that authored Input and generated priority Guard are separate"
        )
    if not fallback_witnesses:
        failures.append(
            "the README example does not prove that fallback has no Input and renders as [otherwise]"
        )

    if failures:
        raise AssertionError(
            "README state diagram does not satisfy the semantic publication contract.\n"
            + "\n".join(f"- {item}" for item in failures)
            + f"\naction_target_analysis: {independence}"
            + f"\nenabling_cases: {cases}"
        )


def compare_images(
    generated_path: Path,
    committed_path: Path,
) -> tuple[int, float, int, tuple[int, int]]:
    with (
        Image.open(generated_path) as generated_source,
        Image.open(committed_path) as committed_source,
    ):
        generated = generated_source.convert("RGB")
        committed = committed_source.convert("RGB")
        if generated.size != committed.size:
            raise AssertionError(
                "README state-transition PNG dimensions differ from the "
                "compiler-derived rendering.\n"
                f"committed: {committed.size}\n"
                f"generated: {generated.size}"
            )
        if generated.size != EXPECTED_SIZE:
            raise AssertionError(
                "README state-transition PNG dimensions changed unexpectedly.\n"
                f"expected: {EXPECTED_SIZE}\n"
                f"actual: {generated.size}"
            )

        difference = ImageChops.difference(generated, committed)
        red, green, blue = difference.split()
        changed_mask = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        mask_histogram = changed_mask.histogram()
        pixel_count = generated.width * generated.height
        changed_pixels = pixel_count - mask_histogram[0]

        histogram = difference.histogram()
        absolute_sum = sum(
            delta * histogram[channel * 256 + delta]
            for channel in range(3)
            for delta in range(256)
        )
        mean_absolute_delta = absolute_sum / (pixel_count * 3)
        max_channel_delta = max(
            (
                delta
                for channel in range(3)
                for delta in range(255, -1, -1)
                if histogram[channel * 256 + delta]
            ),
            default=0,
        )
        return (
            changed_pixels,
            mean_absolute_delta,
            max_channel_delta,
            generated.size,
        )


def main() -> None:
    verify_readme_semantics()

    if os.environ.get("UPDATE_README_STATE_DIAGRAM") == "1":
        COMMITTED_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(GENERATED_PATH, COMMITTED_PATH)
        print(f"updated {COMMITTED_PATH.relative_to(ROOT)}")
        return

    changed_pixels, mean_absolute_delta, max_channel_delta, size = compare_images(
        GENERATED_PATH,
        COMMITTED_PATH,
    )
    pixel_count = size[0] * size[1]
    changed_fraction = changed_pixels / pixel_count
    accepted = (
        changed_pixels <= MAX_CHANGED_PIXELS
        and mean_absolute_delta <= MAX_MEAN_ABSOLUTE_DELTA
        and max_channel_delta <= MAX_CHANNEL_DELTA
    )
    if not accepted:
        raise AssertionError(
            "README state-transition PNG is stale or was generated from "
            "different semantics.\n"
            f"changed pixels: {changed_pixels}/{pixel_count} "
            f"({changed_fraction:.8%}) [limit {MAX_CHANGED_PIXELS}]\n"
            f"mean absolute channel delta: {mean_absolute_delta:.8f} "
            f"[limit {MAX_MEAN_ABSOLUTE_DELTA}]\n"
            f"maximum channel delta: {max_channel_delta} "
            f"[limit {MAX_CHANNEL_DELTA}]\n"
            "Regenerate and verify it with:\n"
            "node tests/verify_state_diagram_rendering.mjs && \\\n"
            "UPDATE_README_STATE_DIAGRAM=1 "
            "python tests/verify_readme_state_snapshot.py\n"
            "Commit docs/images/glyph-studio-state-transition.png with the "
            "semantic change."
        )

    print(
        "verified operation Action provenance, Action/Target/Output separation, "
        "Input/Guard enabling cases, and README snapshot "
        f"(changed_pixels={changed_pixels}, "
        f"mean_delta={mean_absolute_delta:.8f}, "
        f"max_delta={max_channel_delta})"
    )


if __name__ == "__main__":
    main()
