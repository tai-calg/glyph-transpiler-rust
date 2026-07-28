from __future__ import annotations

import os
import shutil
from pathlib import Path

from PIL import Image, ImageChops

from glyph.compilation import CompilationPipeline
from glyph.io_state_views import build_io_state_views

GENERATED_PATH = Path("build/state-diagram-regression/motor-safety-motor.png")
COMMITTED_PATH = Path("docs/images/glyph-studio-state-transition.png")
MOTOR_SOURCE_PATH = Path("examples/acceptance/motor_safety.glyph")
EXPECTED_SIZE = (1800, 1100)

# READMEで公開するMotor Safety例は、Actionを命令、Target Stateを状態として
# 明示的に分離する。文字列が異なるだけのStop/Stoppedは許容しない。
REQUIRED_ACTION_TARGET_PAIRS = {
    ("DisableMotor", "Stopped"),
    ("SetMotorPower(normalize(input.raw))", "Running"),
}
FORBIDDEN_ACTION_TARGET_PAIRS = {
    ("Stop", "Stopped"),
    ("Drive(normalize(input.raw))", "Running"),
}

# Chromium can vary a few anti-aliased pixels between otherwise equivalent runs.
# These limits accept the observed rasterization noise while rejecting changed text,
# layout, state nodes, or transition semantics.
MAX_CHANGED_PIXELS = 256
MAX_MEAN_ABSOLUTE_DELTA = 0.001
MAX_CHANNEL_DELTA = 32


def action_display(transition: dict[str, object]) -> str:
    action = transition.get("action")
    if not isinstance(action, dict):
        return ""
    return str(action.get("display") or action.get("expression") or "")


def verify_readme_semantics() -> None:
    output = CompilationPipeline().compile_text(
        MOTOR_SOURCE_PATH.read_text(encoding="utf-8"),
        source_name=str(MOTOR_SOURCE_PATH),
    )
    views = build_io_state_views(output.model, output.diagrams.ir)
    machine = views["state"]["machines"][0]
    pairs = {
        (action_display(transition), str(transition.get("target_state") or ""))
        for transition in machine["transitions"]
        if transition.get("input_preimage")
    }

    missing = REQUIRED_ACTION_TARGET_PAIRS - pairs
    forbidden = FORBIDDEN_ACTION_TARGET_PAIRS & pairs
    if missing or forbidden:
        raise AssertionError(
            "README Motor Safety semantics do not separate command Actions from "
            "Target States.\n"
            f"required but missing: {sorted(missing)}\n"
            f"forbidden but present: {sorted(forbidden)}\n"
            f"compiled pairs: {sorted(pairs)}"
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
        print(f"updated {COMMITTED_PATH}")
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
        "verified README state-transition semantics and snapshot "
        f"(changed_pixels={changed_pixels}, "
        f"mean_delta={mean_absolute_delta:.8f}, "
        f"max_delta={max_channel_delta})"
    )


if __name__ == "__main__":
    main()
