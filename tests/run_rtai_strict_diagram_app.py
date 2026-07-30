from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from glyph import diagram_app
from glyph.readable_diagram_app import prepare_diagram_app
from glyph.transition_analysis import (
    VerifiedEffectContractRegistry,
    build_strict_io_state_views,
    read_only_identity_contract,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    contracts = VerifiedEffectContractRegistry(
        defaults=(
            (
                "actuator",
                read_only_identity_contract(
                    "actuator",
                    "state",
                    source="strict UI campaign: reviewed identity actuator",
                ),
            ),
        )
    )

    def strict_views(model: object, execution: object) -> dict[str, object]:
        return build_strict_io_state_views(  # type: ignore[arg-type]
            model,
            execution,
            contracts,
        )

    prepare_diagram_app()
    return diagram_app.run_diagram_app(args.input, view_builder=strict_views)


if __name__ == "__main__":
    raise SystemExit(main())
