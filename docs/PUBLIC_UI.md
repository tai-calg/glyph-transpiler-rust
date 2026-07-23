# Public Glyph UI Platform

## Status

The UI platform is an alpha public API built on the pure Glyph runtime. It is intended for local tools, prototypes, internal dashboards, demonstrations, and renderer experimentation.

It does not execute `!` effect boundaries, `~` native implementations, arbitrary Python callbacks, or untrusted plugins.

## Architecture

```text
Glyph source
  -> validated CompilationModel
  -> glyph.ui-ir v1
  -> optional glyph.ui-manifest v1
  -> GlyphUiProject
  -> RendererRegistry
  -> Gradio or another registered renderer
```

Application formulas remain in Glyph. The manifest changes presentation metadata only.

## Installation

Compiler and UI IR only:

```bash
python3 -m pip install .
```

Gradio renderer:

```bash
python3 -m pip install '.[ui]'
```

## CLI

```bash
glyph-gradio examples/gradio_profile.glyph \
  --manifest examples/gradio_profile.ui.json
```

Inspect without importing Gradio:

```bash
glyph-gradio examples/gradio_profile.glyph \
  --manifest examples/gradio_profile.ui.json \
  --check \
  --ui-ir-output build/profile-ui-ir.json
```

The server binds to `127.0.0.1` by default. Exposing it on another interface is an explicit operator decision through `--host`.

## Python API

```python
from glyph.ui_public import open_ui_project

with open_ui_project(
    "examples/gradio_profile.glyph",
    manifest="examples/gradio_profile.ui.json",
) as project:
    print(project.ui_ir_json())
    project.start_watching()
    demo = project.render("gradio")
```

The supported public symbols are:

```text
glyph.ui_public.GlyphUiProject
glyph.ui_public.RendererRegistry
glyph.ui_public.UiRenderer
glyph.ui_public.open_ui_project
glyph.ui_public.renderers

glyph.ui_manifest.UiManifest
glyph.ui_manifest.UiNodeOverride
glyph.ui_manifest.UiManifestError
glyph.ui_manifest.load_ui_manifest
glyph.ui_manifest.parse_ui_manifest
glyph.ui_manifest.apply_ui_manifest
```

Compiler AST classes, private renderer helpers, `LivePureGlyphRuntime` internals, and underscore-prefixed names are not stable public API.

## Renderer extension

A renderer receives a live runtime and immutable UI application:

```python
from glyph.ui_public import renderers


def render_text(runtime, application, **options):
    return {
        "action": application.action.name,
        "inputs": [node.to_dict() for node in application.action.inputs],
    }


renderers.register("text", render_text)
```

Registration is explicit. A name cannot be replaced unless `replace=True` is passed.

Third-party renderers should:

- consume `UiApplication` rather than compiler internals;
- preserve semantic node IDs;
- reconstruct arguments from node paths;
- call `LivePureGlyphRuntime.invoke` rather than duplicating Glyph formulas;
- fail explicitly for unsupported widgets;
- avoid importing optional frontend dependencies at package import time.

## UI manifest

The manifest is JSON and has no executable fields.

```json
{
  "schema": "glyph.ui-manifest",
  "version": 1,
  "title": "Profile Access Inspector",
  "function": "render",
  "locale": "en",
  "nodes": {
    "input:profile.age": {
      "label": "Age",
      "minimum": 0,
      "maximum": 130,
      "default": 30
    }
  }
}
```

Allowed node properties:

- `label`
- `description`
- `widget`
- `default`
- `minimum`
- `maximum`
- `choices`

Unknown root fields, unknown node properties, invalid widget names, invalid ranges, and unknown semantic node IDs are rejected. There is intentionally no callback, import, module, expression, template, JavaScript, Python, shell, or command field.

## Compatibility contract

### `glyph.ui-ir`

- Schema name: `glyph.ui-ir`
- Current version: `1`
- Semantic IDs are derived from role and typed path, for example `input:profile.age`.
- Consumers must reject unsupported major versions.
- Additive optional fields may be introduced within version 1.
- Removal or semantic reinterpretation requires a schema version increment.

### `glyph.ui-manifest`

- Schema name: `glyph.ui-manifest`
- Current version: `1`
- Unknown fields are rejected to catch spelling errors and prevent silent unsafe expansion.
- Node overrides reference UI IR semantic IDs rather than display order.

### Python API

The names listed in the Python API section are the alpha compatibility surface. Changes still may occur before 1.0, but they require a changelog entry and migration note.

## Live reload

Function-body-compatible changes may produce a new active World without rebuilding the frontend component graph. Type and function-signature changes are migration-class changes and are not silently projected into the existing browser form.

After a committed schema change, restart the renderer so it can build a new component graph from the new UI IR.

## Security boundary

The public UI platform is not a sandbox for hostile Glyph source.

Current protections:

- no arbitrary Python callbacks in manifests;
- no automatic implementation of `!` or `~`;
- no eager import of Gradio for inspection commands;
- local-only default host binding;
- explicit renderer registration;
- strict manifest key validation;
- typed runtime validation at invocation boundaries;
- last-good World retention after compile errors.

Deployments exposed to a network must add authentication, TLS termination, request limits, and process isolation outside Glyph.

## Publication checklist

Before tagging a release:

1. ordinary compiler CI passes;
2. Gradio component-graph CI passes;
3. `python -m build` succeeds;
4. wheel installs in a clean environment;
5. `glyph-gradio --help` succeeds;
6. UI IR and manifest fixtures remain deterministic;
7. public API and schema changes are recorded in the changelog;
8. examples contain no secrets or external service dependencies.
