# Glyph Public UI SDK

## Purpose

The public UI SDK turns a validated pure Glyph function into a backend-neutral UI contract and delegates rendering to a registered backend.

```text
Glyph source
  -> validated CompilationModel
  -> glyph.ui-ir v1
  -> glyph.ui API v1 / UiProject
  -> backend protocol v1
  -> Gradio or a third-party backend
```

Compiler AST classes are not the public rendering contract. External renderers consume `UiApplication`, serialized `glyph.ui-ir`, and the `UiProject` lifecycle.

The existing package-root API remains unchanged. UI functionality is published under the explicit `glyph.ui` namespace.

## Installation

Core compiler and UI IR:

```bash
python3 -m pip install glyph-rust
```

Built-in Gradio backend:

```bash
python3 -m pip install "glyph-rust[ui]"
```

Importing `glyph` or `glyph.ui` does not import Gradio or pandas. Optional dependencies are loaded only when the `gradio` backend is created.

## Python API

### Compile UI IR without a server

```python
from glyph.ui import compile_ui_source

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

### Open a file-backed live project

```python
from glyph.ui import open_ui

with open_ui("design.glyph", function_name="render") as project:
    project.launch("gradio")
```

`UiProject` owns:

- `LivePureGlyphRuntime`
- active `UiApplication`
- component-schema fingerprint
- backend registry
- optional file watcher
- explicit restart and close lifecycle

### Build without launching

```python
from glyph.ui import open_ui

with open_ui("design.glyph") as project:
    blocks = project.build("gradio")
```

### Invoke the exposed Glyph action

```python
from glyph.ui import open_ui

with open_ui("profile.glyph") as project:
    result = project.invoke(
        {"profile": {"name": "Ada", "age": 35, "active": True}}
    )
    print(result.world_version)
    print(result.to_python())
```

## CLI

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

Backend-specific values use `KEY=VALUE`; JSON literals are decoded when possible.

```bash
glyph-ui design.glyph \
  --backend custom \
  --backend-option compact=true \
  --backend-option locale=ja
```

## Independent compatibility versions

| Contract | Version | Purpose |
|---|---:|---|
| `glyph.ui-ir` | 1 | serialized application/component semantics |
| Python UI API | 1 | `UiProject`, compile/open functions, lifecycle |
| backend protocol | 1 | third-party renderer integration |

These versions are independent of the Glyph language version. A language release does not automatically break UI backends.

## UI IR codec and validation

Do not construct UI dataclasses from untrusted JSON directly.

```python
from glyph.ui_schema import loads_ui_application

application = loads_ui_application(text)
```

The codec validates:

- exact schema and supported version
- node kind and input/output role
- non-empty ID, path, label, and type
- unique semantic IDs and paths
- child path nesting
- numeric range consistency
- choices required by select/badge nodes
- non-empty object nodes

The component fingerprint excludes source locations. Moving a declaration or changing only a function body therefore does not rebuild the browser component tree.

## Live schema behavior

Function-body edit:

```text
source save
  -> new executable World
  -> same component fingerprint
  -> current browser UI remains valid
  -> next invocation uses the new World
```

Type or signature edit:

```text
source save
  -> candidate UI IR
  -> different component fingerprint
  -> project.requires_restart = true
  -> current component graph remains active
```

Explicit inspection and restart:

```python
state = project.inspect_schema(force=True)
if state.requires_restart:
    project.restart()
    rebuilt = project.build("gradio")
```

The SDK does not silently mutate an existing component tree into an incompatible function signature.

## Backend protocol

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

Direct registration:

```python
from glyph.ui import open_ui
from glyph.ui_backends import BackendRegistry

registry = BackendRegistry()
registry.register("terminal", TerminalBackend)

with open_ui("design.glyph", registry=registry) as project:
    project.launch("terminal")
```

Third-party packages can publish an entry point:

```toml
[project.entry-points."glyph.ui_backends"]
terminal = "my_glyph_backend:TerminalBackend"
```

The target may be a backend instance, backend class, or zero-argument factory. Explicit registrations take precedence over discovered names.

## Built-in Gradio backend

```python
from glyph.ui import open_ui
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

The generic renderer is conservative:

- numbers -> numeric control / metric
- booleans -> checkbox / status
- text -> textbox / text card
- products -> recursive form / nested result card
- unit sums -> dropdown / badge
- payload sums, recursive types, and unknown types -> explicit JSON boundary

It does not infer units, slider ranges, chart meaning, or business semantics from field names.

## Security and execution boundary

The SDK executes only the supported pure Glyph subset through `PureGlyphProgram`.

It does not:

- execute arbitrary Python callbacks from Glyph source
- guess implementations for `!` effect boundaries
- execute `~` native Rust bodies
- import a rendering backend merely to compile UI IR
- auto-approve type or Resource migration
- claim native/JIT hot replacement

Unsupported boundaries fail explicitly.

## Publication gates

A publishable build must pass:

1. ordinary compiler, generated Rust, demos, and Clippy CI
2. UI IR and public API tests without Gradio installed
3. Python 3.10 and 3.12 compatibility
4. Gradio 6 component-graph tests with the optional extra
5. sdist and wheel construction
6. Twine metadata validation
7. clean-environment wheel installation
8. `glyph-ui` and `glyph-gradio` smoke tests
9. `py.typed` inclusion
10. installed-wheel Gradio graph construction
11. serialized UI IR round-trip tests

The current SDK is alpha. The stable public surfaces are `glyph.ui-ir v1`, `glyph.ui` API v1, and backend protocol v1. Compiler internals and backend implementation helpers remain private.
