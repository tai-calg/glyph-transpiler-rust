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


def versioned_payload(
    schema: str,
    payload: Mapping[str, object],
    *,
    version: int = IR_SCHEMA_VERSION,
) -> dict[str, object]:
    """Return a deterministic top-level schema envelope without nesting payload data."""

    if "schema" in payload or "version" in payload:
        raise ValueError("schema payload must not define reserved keys 'schema' or 'version'")
    return {"schema": schema, "version": version, **payload}
