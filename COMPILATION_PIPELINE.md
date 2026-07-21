# Compilation Pipeline and IR Schemas

## Authoritative API

`CompilationPipeline` is the authoritative source-to-artifact API.

```python
from glyph import CompilationPipeline

outputs = CompilationPipeline().compile_text(
    source,
    source_name="controller.glyph",
)

model = outputs.model
rust = outputs.artifacts.logic
diagrams = outputs.diagrams.files
typed_design = outputs.design_json
```

One call performs preprocessing, parsing, lowering, validation, semantic analysis, Rust generation, and IR generation. The parsed `CompilationModel` is shared by every downstream generator.

```text
original Glyph
  ↓ raw preprocessor
expanded Glyph
  ↓ syntax extraction and lowering
validated CompilationModel
  ├── RustArtifacts
  ├── Architecture IR
  ├── Algorithm IR
  ├── Execution IR
  ├── source maps and Mermaid
  └── typed design JSON
```

Studio, watch mode, and `glyphc.py` use this pipeline. `IncrementalCompiler` caches the complete output by source digest, so an unchanged source is not reparsed.

## Compatibility APIs

The following public APIs delegate to `CompilationPipeline`:

```python
from glyph import compile_outputs, compile_diagram_bundle, write_diagram_bundle
```

Older lower-level modules remain implementation details. New integrations should import from `glyph`, not from `glyph.mermaid` or private helper functions.

## Versioned machine-readable artifacts

Every public machine-readable top-level artifact has a schema identifier and integer version.

| Artifact | Schema | Version |
|---|---|---:|
| `typed-ast.json` | `glyph.typed-design` | 1 |
| `architecture-ir.json` | `glyph.architecture-ir` | 1 |
| `algorithm-ir.json` | `glyph.algorithm-ir` | 1 |
| `execution-ir.json` | `glyph.execution-ir` | 1 |
| `source-map.json` | `glyph.source-map` | 1 |
| `preprocessor-map.json` | `glyph.preprocessor-map` | 1 |

Example:

```json
{
  "schema": "glyph.algorithm-ir",
  "version": 1,
  "source_name": "controller.glyph",
  "functions": []
}
```

A consumer must reject unsupported major integer versions rather than guessing the meaning of changed fields. Additive fields that preserve version-1 semantics may be ignored by readers.

## Studio ownership

Studio has one frontend implementation:

```text
glyph/studio.py      HTTP server, source persistence, watch and snapshots
glyph/studio_ui.py   canonical HTML/CSS/JavaScript frontend
glyph/studio_manual.py manual.rs ownership rules
```

`studio.py` imports `STUDIO_HTML` from `studio_ui.py`; it contains no embedded fallback UI. The canonical frontend includes Architecture, State, Logic, Flow, Time, Rust, Host, Manual, AST, Symbols, and Artifacts views.

## Invariants

1. One source digest is parsed and validated at most once per `IncrementalCompiler` cache entry.
2. Rust, diagrams, and typed design JSON originate from the same `CompilationModel`.
3. Public JSON artifacts contain `schema` and `version`.
4. Source references exposed to users point to the original `.glyph` file after preprocessing remapping.
5. Studio serves only `glyph/studio_ui.py`.
6. Compatibility wrappers may return subsets, but may not create an independent compilation path.
