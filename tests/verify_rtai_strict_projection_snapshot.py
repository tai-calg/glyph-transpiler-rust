from __future__ import annotations

import json
from pathlib import Path

from glyph.compilation import CompilationPipeline
from glyph.transition_analysis import (
    VerifiedEffectContractRegistry,
    build_strict_io_state_views,
    read_only_identity_contract,
)


SOURCE = Path("examples/acceptance/rtai_strict_projection.glyph")
OUTPUT = Path("build/rtai-strict-projection/io-state-views.json")


def main() -> None:
    compiled = CompilationPipeline().compile_text(
        SOURCE.read_text(encoding="utf-8"),
        source_name=str(SOURCE),
    )
    contracts = VerifiedEffectContractRegistry(
        defaults=(
            (
                "actuator",
                read_only_identity_contract(
                    "actuator",
                    "state",
                    source="strict snapshot: reviewed read-only identity actuator",
                ),
            ),
        )
    )
    views = build_strict_io_state_views(
        compiled.model,
        compiled.diagrams.ir,
        contracts,
    )
    campaign = views["strict_projection_campaign"]
    if campaign.get("ready") is not True:
        raise AssertionError(
            "strict RTAI projection campaign is not ready: "
            + json.dumps(campaign, ensure_ascii=False, sort_keys=True)
        )
    if campaign.get("legacy_fallback_allowed") is not False:
        raise AssertionError("strict campaign unexpectedly allows legacy fallback")

    transition_count = 0
    for machine in views["state"]["machines"]:
        report = machine.get("strict_projection_campaign", {})
        if report.get("ready") is not True:
            raise AssertionError(f"machine strict campaign is not ready: {report!r}")
        for transition in machine.get("transitions", []):
            transition_count += 1
            if transition.get("legacy_system_action_fallback_allowed") is not False:
                raise AssertionError("transition allows legacy System Action fallback")
            if transition.get("execution_action_bindings") != []:
                raise AssertionError("legacy execution_action_bindings remain published")
            if transition.get("execution_contexts") != []:
                raise AssertionError("legacy execution_contexts remain published")
            if transition.get("system_action_projection_source") != (
                "rtai-execution-evidence-v2"
            ):
                raise AssertionError("System Action does not use native RTAI Evidence")
            if transition.get("system_action") is None:
                raise AssertionError("ready transition has no strict System Action")

    if transition_count == 0:
        raise AssertionError("strict snapshot contains no transitions")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(views, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ready": True,
                "transition_count": transition_count,
                "output": str(OUTPUT),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
