# Glyph Public UI SDK

## 1. Purpose

The public UI SDK turns a validated pure Glyph function into a backend-neutral UI contract and then delegates rendering to a registered backend.

```text
Glyph source
  -> validated CompilationModel
  -> glyph.ui-ir v1
  -> UiProject
  -> backend protocol v1
  -> Gradio or third-party backend
```

The SDK does not expose compiler AST objects as a rendering contract. External renderers consume `UiApplication` / serialized `glyph.ui-ir` and the stable `UiProject` lifecycle.

## 2. Installation

Core compiler and UI IR only:

```bash
python3 -m pip install glyph-rust
```

Built-in Gradio backend:

```bash
python3 -m pip install "glyph-rust[ui]"
```

The core package does not import Gradio or pandas. Optional UI dependencies are loaded only when the `gradio` backend is created.

## 3. Public Python API

### Compile UI IR without a server

```python
from glyph import compile_ui_source

application = compile_ui_source(
    """
    *Input(name:S,enabled:B)
    *View(name:S,enabled:B)
    >render(input:Input):View=View(input.name,input.enabled)
    """,
    source_name="memory.glyph",
)

print(application.to_json())
```

### Open a file-backed live application

```python
from glyph import open_ui

with open_ui("design.glyph", function_name="render") as project:
    project.launch("gradio")
```

`UiProject` owns:

- `LivePureGlyphRuntime`
- active `UiApplication`
- schema compatibility fingerprint
- backend registry
- optional file watcher
- explicit close/restart lifecycle

### Build without launching

```python
with open_ui("design.glyph") as project:
    blocks = project.build("gradio")
```

### Invoke the exposed Glyph action directly

```python
with open_ui("profile.glyph") as project:
    result = project.invoke(
        {"profile": {"name": "Ada", "age": 35, "active": True}}
    )
    print(result.world_version)
    print(result.to_python())
```

## 4. Public CLI

```bash
glyph-ui design.glyph
glyph-ui design.glyph --function calculate
glyph-ui design.glyph --check
glyph-ui design.glyph --ui-ir-output build/ui-ir.json
glyph-ui --list-backends
```

Compatibility alias:

```bash
glyph-gradio design.glyph
```

Backend-specific options use JSON-compatible `KEY=VALUE` values:

```bash
glyph-ui design.glyph \
  --backend custom \
  --backend-option compact=true \
  --backend-option locale=ja
```

## 5. Compatibility contracts

The public UI surface has three independent versions.

| Contract | Version | Purpose |
|---|---:|---|
| `glyph.ui-ir` | 1 | serialized application and component semantics |
| Python UI API | 1 | `UiProject`, compile/open functions, lifecycle |
| backend protocol | 1 | third-party renderer integration |

A language release does not automatically change these versions. A breaking change to one contract increments only that contract.

## 6. UI IR serialization

Use the schema codec rather than constructing dataclasses from arbitrary JSON.

```python
from glyph.ui_schema import loads_ui_application

application = loads_ui_application(text)
```

The loader validates:

- exact schema and version
- node kinds and roles
- non-empty IDs, paths, labels, and types
- unique semantic IDs and paths
- nested child paths
- numeric range consistency
- required choices for select/badge nodes
- non-empty object nodes

The component fingerprint excludes source location. Moving a declaration or changing only a function body therefore does not invalidate the browser component tree.

## 7. Live edit behavior

Function-body-only edit:

```text
source save
  -> new executable World
  -> same component fingerprint
  -> existing browser UI remains valid
  -> next invocation uses the new World
```

Type or signature edit:

```text
source save
  -> candidate UI IR
  -> different component fingerprint
  -> project.requires_restart = true
  -> existing component graph is retained
```

Inspect explicitly:

```python
state = project.inspect_schema(force=True)
if state.requires_restart:
    project.restart()
    app = project.build("gradio")
```

The SDK never mutates an already-rendered component graph into an incompatible signature.

## 8. Backend protocol

A backend implements two methods and declares the protocol version.

```python
from glyph.ui_backends import BACKEND_API_VERSION

class TerminalBackend:
    name = "terminal"
    api_version = BACKEND_API_VERSION

    def build(self, project, **options):
        return {"ui_ir": project.ui_ir(), "options": options}

    def launch(self, project, **options):
        return self.build(project, **options)
```

Register directly:

```python
from glyph.ui_backends import BackendRegistry
from glyph import open_ui

registry = BackendRegistry()
registry.register("terminal", TerminalBackend)

with open_ui("design.glyph", registry=registry) as project:
    project.launch("terminal")
```

### Third-party package discovery

External distributions can publish an entry point:

```toml
[project.entry-points."glyph.ui_backends"]
terminal = "my_glyph_backend:TerminalBackend"
```

The object may be a backend instance, backend class, or zero-argument factory. Duplicate names do not overwrite explicitly registered factories.

## 9. Built-in Gradio backend

The optional backend is exposed through `GradioBackend` and `GradioOptions`.

```python
from glyph import open_ui
from glyph.gradio_backend import GradioOptions

with open_ui("design.glyph") as project:
    project.launch(
        "gradio",
        options=GradioOptions(
            server_name="127.0.0.1",
            server_port=7860,
            inbrowser=False,
            watch=True,
        ),
    )
```

The generic renderer remains conservative:

- numbers -> numeric controls / metrics
- booleans -> checkbox / status
- text -> textbox / text card
- products -> recursive forms / nested result cards
- unit sums -> dropdown / badge
- payload sums and unknown structures -> explicit JSON boundary

It does not infer units, slider ranges, chart meanings, or business semantics from field names.

## 10. Security and execution boundary

The public UI SDK executes only the supported pure Glyph subset through `PureGlyphProgram`.

It does not:

- execute arbitrary Python callbacks from source
- guess implementations for `!` effect boundaries
- execute `~` native Rust bodies
- dynamically import a backend merely by compiling UI IR
- auto-approve type/resource migration
- claim native/JIT hot replacement

Unsupported execution boundaries fail explicitly.

## 11. Packaging and release gates

A publishable build must pass:

1. ordinary compiler and Rust CI
2. UI IR and public API tests without Gradio installed
3. Gradio 6 component-graph tests with the optional extra installed
4. wheel and sdist construction
5. fresh-environment wheel import
6. `glyph-ui` and `glyph-gradio` console-script smoke tests
7. typed package marker inclusion
8. serialized UI IR round-trip tests

The current SDK is alpha. `glyph.ui-ir v1`, Python UI API v1, and backend protocol v1 are the intended public compatibility boundaries; unsupported internals remain private.
