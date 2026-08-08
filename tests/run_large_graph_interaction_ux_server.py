from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from glyph.desktop_server import run_studio_app
from glyph.io_state_views import build_io_state_views


STATE_COUNT = 64
EDGES_PER_STATE = 3


def large_graph_view_builder(model: object, ir: object) -> dict[str, object]:
    """Keep the real compiler/UI pipeline while scaling only the rendered state view."""

    views = build_io_state_views(model, ir)
    machines = views.get("state", {}).get("machines", [])
    if not machines:
        raise RuntimeError("large-graph UX fixture requires one compiled machine")

    base = deepcopy(machines[0])
    state_template = deepcopy(base["states"][0])
    transition_template = deepcopy(base["transitions"][0])

    states: list[dict[str, object]] = []
    for index in range(STATE_COUNT):
        item = deepcopy(state_template)
        item["name"] = f"S{index}"
        item["reachable"] = True
        item["terminal"] = "success" if index == 1 else "failure" if index == STATE_COUNT - 1 else None
        item["source"] = {"line": 20 + index}
        states.append(item)

    transitions: list[dict[str, object]] = []
    transition_index = 0
    for source_index in range(STATE_COUNT):
        for offset, label in ((1, "forward"), (-1, "back"), (7, "jump")):
            item = deepcopy(transition_template)
            target_index = (source_index + offset) % STATE_COUNT
            transition_index += 1
            item.update(
                {
                    "id": f"T{transition_index}",
                    "source_state": f"S{source_index}",
                    "target_state": f"S{target_index}",
                    "condition": f"input.{label}",
                    "condition_raw": f"input.{label}",
                    "display_label": f"input.{label}",
                    "source": {"line": 100 + transition_index},
                    "source_reachable": True,
                    "expanded_from_wildcard": False,
                    "event": "",
                    "trigger": None,
                    "guards": [f"input.{label}"],
                    "unclassified_conditions": [],
                    "action": None,
                    "outcome": "success" if target_index == 1 else "failure" if target_index == STATE_COUNT - 1 else None,
                }
            )
            transitions.append(item)

    base.update(
        {
            "name": "LargeGraph",
            "state_type": "LargeState",
            "selector": "state.mode",
            "next_function": "large_step",
            "initial_state": "S0",
            "success_state": "S1",
            "failure_state": f"S{STATE_COUNT - 1}",
            "states": states,
            "transitions": transitions,
            "unreachable_states": [],
            "unreachable_branches": [],
            "diagnostics": [],
            "analysis": {
                "function_closure": ["large_step"],
                "raw_transition_count": len(transitions),
                "normalized_transition_count": len(transitions),
                "wildcard_transition_count": 0,
                "reachable_state_count": STATE_COUNT,
                "state_count": STATE_COUNT,
            },
        }
    )

    views["state"]["machines"] = [base]
    views["summary"]["machines"] = 1
    views["summary"]["state_warnings"] = 0
    views["large_graph_fixture"] = {
        "state_count": STATE_COUNT,
        "transition_count": len(transitions),
        "edges_per_state": EDGES_PER_STATE,
    }
    return views


def main() -> int:
    source = REPOSITORY_ROOT / "examples" / "state_diagrams" / "traffic_light.glyph"
    return run_studio_app(
        source,
        open_browser=False,
        view_builder=large_graph_view_builder,
    )


if __name__ == "__main__":
    raise SystemExit(main())
