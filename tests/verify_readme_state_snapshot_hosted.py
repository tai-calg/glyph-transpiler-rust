from __future__ import annotations

from verify_readme_state_snapshot import (
    ANTIALIAS_CHANNEL_FLOOR,
    COMMITTED_PATH,
    GENERATED_PATH,
    STRUCTURAL_BLUR_RADIUS,
    compare_images,
    verify_readme_semantics,
)

MAX_CHANGED_PIXELS = 8_000
MAX_MEAN_ABSOLUTE_DELTA = 0.15


def main() -> None:
    verify_readme_semantics()
    changed_pixels, mean_absolute_delta, max_channel_delta, size = compare_images(
        GENERATED_PATH,
        COMMITTED_PATH,
    )
    pixel_count = size[0] * size[1]
    changed_fraction = changed_pixels / pixel_count

    # Hosted Chromium/font stacks can move a small number of high-contrast edge
    # pixels by a large channel value. A single-pixel maximum is therefore not a
    # useful structural gate. The changed-pixel budget and whole-image mean remain
    # tight enough to reject moved nodes, labels, and routes; semantic contracts are
    # verified independently above.
    accepted = (
        changed_pixels <= MAX_CHANGED_PIXELS
        and mean_absolute_delta <= MAX_MEAN_ABSOLUTE_DELTA
    )
    if not accepted:
        raise AssertionError(
            "README state-transition PNG is stale or structurally different from "
            "the fresh compiler-derived hosted rendering.\n"
            f"normalized significant changed pixels: {changed_pixels}/{pixel_count} "
            f"({changed_fraction:.8%}) [limit {MAX_CHANGED_PIXELS}]\n"
            f"normalized significant mean absolute channel delta: "
            f"{mean_absolute_delta:.8f} [limit {MAX_MEAN_ABSOLUTE_DELTA}]\n"
            f"normalized maximum significant channel delta (diagnostic only): "
            f"{max_channel_delta}\n"
            f"Gaussian normalization radius: {STRUCTURAL_BLUR_RADIUS}\n"
            f"ignored normalized antialias channel floor: {ANTIALIAS_CHANNEL_FLOOR}"
        )

    print(
        "verified hosted README raster baseline after semantic validation "
        f"(significant_changed_pixels={changed_pixels}, "
        f"significant_mean_delta={mean_absolute_delta:.8f}, "
        f"max_delta_diagnostic={max_channel_delta}, "
        f"blur_radius={STRUCTURAL_BLUR_RADIUS}, "
        f"antialias_floor={ANTIALIAS_CHANNEL_FLOOR})"
    )


if __name__ == "__main__":
    main()
