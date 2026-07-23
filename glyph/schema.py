from __future__ import annotations

from collections.abc import Mapping


IR_SCHEMA_VERSION = 1

ARCHITECTURE_IR_SCHEMA = "glyph.architecture-ir"
ALGORITHM_IR_SCHEMA = "glyph.algorithm-ir"
EXECUTION_IR_SCHEMA = "glyph.execution-ir"
SEMANTIC_MODEL_SCHEMA = "glyph.semantic-model"
TYPED_DESIGN_SCHEMA = "glyph.typed-design"
SOURCE_MAP_SCHEMA = "glyph.source-map"
STUDIO_STATE_SCHEMA = "glyph.studio-state"

# Glyph 0.4 public contracts. These identifiers, versions, and top-level
# shapes are frozen for the 0.4 release line. Incompatible changes require
# a new schema version instead of editing version 1 in place.
CAPABILITY_IR_SCHEMA = "glyph.capability-ir"
RESOURCE_FLOW_IR_SCHEMA = "glyph.resource-flow-ir"
CONTRACTS_IR_SCHEMA = "glyph.contracts"
RUNTIME_CONTRACT_IR_SCHEMA = "glyph.runtime-contract-ir"
VERIFICATION_REPORT_SCHEMA = "glyph.verification-report"
HOST_REQUIREMENTS_IR_SCHEMA = "glyph.host-requirements"
COMPLIANCE_REPORT_SCHEMA = "glyph.compliance-report"
COMPATIBILITY_REPORT_SCHEMA = "glyph.compatibility-report"
STABILIZATION_REPORT_SCHEMA = "glyph.stabilization-report"

GLYPH04_PUBLIC_SCHEMAS: dict[str, tuple[str, int]] = {
    "capability-ir.json": (CAPABILITY_IR_SCHEMA, IR_SCHEMA_VERSION),
    "resource-flow-ir.json": (RESOURCE_FLOW_IR_SCHEMA, IR_SCHEMA_VERSION),
    "contracts-ir.json": (CONTRACTS_IR_SCHEMA, IR_SCHEMA_VERSION),
    "runtime-contract-ir.json": (RUNTIME_CONTRACT_IR_SCHEMA, IR_SCHEMA_VERSION),
    "verification-report.json": (VERIFICATION_REPORT_SCHEMA, IR_SCHEMA_VERSION),
    "host-requirements-ir.json": (HOST_REQUIREMENTS_IR_SCHEMA, IR_SCHEMA_VERSION),
}

GLYPH04_PUBLIC_SCHEMA_KEYS: dict[str, frozenset[str]] = {
    "capability-ir.json": frozenset(
        {"schema", "version", "resources", "functions", "aggregates", "operations"}
    ),
    "resource-flow-ir.json": frozenset({"schema", "version", "transitions"}),
    "contracts-ir.json": frozenset(
        {"schema", "version", "declarations", "applications"}
    ),
    "runtime-contract-ir.json": frozenset(
        {
            "schema",
            "version",
            "worlds",
            "protocols",
            "handlers",
            "laws",
            "rows",
            "applications",
        }
    ),
    "verification-report.json": frozenset(
        {"schema", "version", "summary", "items"}
    ),
    "host-requirements-ir.json": frozenset(
        {"schema", "version", "representations", "operations", "invariants"}
    ),
}


def versioned_payload(
    schema: str,
    payload: Mapping[str, object],
    *,
    version: int = IR_SCHEMA_VERSION,
) -> dict[str, object]:
    """Return a deterministic schema envelope without nesting payload data."""

    if "schema" in payload or "version" in payload:
        raise ValueError("schema payload must not define reserved keys 'schema' or 'version'")
    return {"schema": schema, "version": version, **payload}
