from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Callable

from . import compilation as _compilation
from .machine_coverage_witness import build_machine_witnesses, machine_witness_payload
from .machine_scenario_witness import build_machine_scenarios, machine_scenario_payload
from .mermaid import DiagramBundle
from .preprocessor import remap_source_lines
from .type_algebra import (
    build_machine_coverage,
    build_type_algebra_ir,
    render_type_algebra_rust,
    tooling_payload,
)


_TOOLING_SCHEMA = "glyph.type-algebra-tooling"
_TOOLING_VERSION = 2
_INSTALLED = False


def _namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**{key: _namespace(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return [_namespace(item) for item in value]
    return value


def _coverage_from_tooling(payload: dict[str, object]) -> tuple[object, ...]:
    reachability_rows = payload.get("machine_state_reachability")
    reachability_by_machine: dict[str, object] = {}
    if isinstance(reachability_rows, list):
        for item in reachability_rows:
            if not isinstance(item, dict):
                continue
            machine = item.get("machine")
            if isinstance(machine, str):
                reachability_by_machine[machine] = _namespace(item)

    output: list[object] = []
    coverage_rows = payload.get("machine_coverage")
    if not isinstance(coverage_rows, list):
        return ()
    for item in coverage_rows:
        if not isinstance(item, dict):
            continue
        coverage = _namespace(item)
        machine = getattr(coverage, "machine", None)
        setattr(coverage, "state_reachability", reachability_by_machine.get(machine))
        output.append(coverage)
    return tuple(output)


def _normalize_tooling_shape(payload: dict[str, object]) -> dict[str, object]:
    payload["schema"] = _TOOLING_SCHEMA
    payload["version"] = _TOOLING_VERSION
    for key in (
        "diagnostics",
        "structural_conversions",
        "machine_coverage",
        "machine_state_reachability",
        "machine_witnesses",
        "machine_scenarios",
    ):
        if not isinstance(payload.get(key), list):
            payload[key] = []
    return payload


def _build_missing_tooling(
    model: object,
    source_name: str,
    bundle: DiagramBundle,
) -> tuple[dict[str, object], dict[str, str]]:
    expanded = model.expanded
    algebra = build_type_algebra_ir(source_name, expanded.program)
    coverage = build_machine_coverage(
        expanded.program,
        expanded.machines,
        bundle.ir,
        algebra,
    )
    witness_reports, witness_rust = build_machine_witnesses(
        expanded.program,
        expanded.machines,
        coverage,
    )
    algebra = remap_source_lines(algebra, model.preprocess)
    coverage = remap_source_lines(coverage, model.preprocess)
    payload = tooling_payload(
        algebra.diagnostics,
        algebra.structural_conversions,
        coverage,
    )
    payload["machine_witnesses"] = machine_witness_payload(witness_reports)
    files = {
        "type-algebra-ir.json": json.dumps(
            algebra.to_dict(), ensure_ascii=False, indent=2
        )
        + "\n",
        "type-algebra.generated.rs": render_type_algebra_rust(algebra),
        "machine-coverage.generated.rs": witness_rust,
    }
    return payload, files


def _append_index(files: dict[str, str], scenario_count: int) -> None:
    index = files.get("index.md", "")
    marker = "## Tooling artifact contract v2"
    if marker in index:
        return
    files["index.md"] = (
        index.rstrip()
        + "\n\n"
        + marker
        + "\n\n"
        + "`type-algebra-tooling.json` is emitted for every successful Glyph "
        + "compilation. `machine-scenarios.generated.rs` contains shortest "
        + "definite paths replayed from `machine.init`.\n\n"
        + f"- generated machine scenario tests: {scenario_count}\n"
    )


def _wrap_build_diagram_bundle(
    original: Callable[..., DiagramBundle],
) -> Callable[..., DiagramBundle]:
    def wrapped(
        model: object,
        source_name: str,
        source_href: str | None = None,
        derived: object | None = None,
    ) -> DiagramBundle:
        bundle = original(model, source_name, source_href, derived)
        files = dict(bundle.files)

        existing = files.get("type-algebra-tooling.json")
        if existing is None:
            payload, generated_files = _build_missing_tooling(model, source_name, bundle)
            files.update(generated_files)
        else:
            parsed = json.loads(existing)
            payload = parsed if isinstance(parsed, dict) else {}

        payload = _normalize_tooling_shape(payload)
        coverage = _coverage_from_tooling(payload)
        scenario_reports, scenario_rust = build_machine_scenarios(
            model.expanded.program,
            model.expanded.machines,
            coverage,
        )
        payload["machine_scenarios"] = machine_scenario_payload(scenario_reports)
        files["machine-scenarios.generated.rs"] = scenario_rust
        files["type-algebra-tooling.json"] = (
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        )
        _append_index(
            files,
            sum(report.generated_tests for report in scenario_reports),
        )
        return DiagramBundle(bundle.ir, bundle.algorithm_ir, files)

    setattr(wrapped, "_glyph_tooling_delivery_v2", True)
    return wrapped


def install_tooling_delivery_v2() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    current = _compilation.build_diagram_bundle
    if not getattr(current, "_glyph_tooling_delivery_v2", False):
        _compilation.build_diagram_bundle = _wrap_build_diagram_bundle(current)
    _INSTALLED = True
