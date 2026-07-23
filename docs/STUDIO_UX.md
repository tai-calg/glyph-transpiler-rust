# Glyph Studio UX

## 1. Objective

Glyph Studio is a design workspace, not only a generated-file viewer. The interface should keep three activities visible and distinct:

1. edit Glyph source,
2. compile or preview the design,
3. inspect orthogonal design views.

The UI must not derive new Glyph semantics. All design views continue to come from the validated typed design and `glyph.studio-views` projection.

## 2. Information architecture

The former flat horizontal tab row is replaced by grouped navigation.

```text
Design
  Overview
  Capability
  Resource
  World/Region
  Protocol
  Handler
  Law/Monitor
  Verification

Program
  Architecture
  State
  Logic
  Flow
  Time

Generated
  Rust
  Host
  Manual
  AST
  Symbols
  Artifacts
```

Each view has a stable title, short purpose statement, item count, and local filter. The last selected view is remembered in browser-local UI state.

## 3. Editing workflow

### Preview

`Preview` compiles the current editor contents without writing the Glyph source file.

```text
editor text
    ↓ POST /api/preview
GlyphStudio.preview_source
    ↓
StudioSnapshot and generated artifacts
```

Preview changes the active Studio snapshot and generated outputs, but the source file remains unchanged.

Keyboard shortcut:

```text
Ctrl/Cmd + Enter
```

### Save

`Save` atomically writes the editor contents to the source file and rebuilds the Studio snapshot.

Keyboard shortcut:

```text
Ctrl/Cmd + S
```

### Reload

`Reload` discards the current editor contents and rebuilds from the file on disk. When the editor is dirty, the UI asks before discarding changes.

### Auto preview

Auto preview is opt-in. It debounces editor changes before invoking the same `/api/preview` endpoint. It never writes the source file.

## 4. State communication

The interface separates two independent states.

### Persistence state

```text
Saved
Unsaved
```

### Compilation state

```text
starting
ready
error
busy: previewing / saving / reloading
```

Compilation diagnostics are shown directly under the editor and in the current view. Diagnostics with a source line navigate to that line.

## 5. Workspace layout

Desktop layout:

```text
source editor | draggable splitter | navigation | active view
```

The editor width is resizable and remembered locally. The editor can be hidden to give diagrams and generated output the full workspace.

Mobile layout:

- editor and viewer become mutually focused surfaces,
- view navigation opens as an overlay,
- selecting a source-linked item opens the editor at that line,
- Escape closes the mobile editor or navigation state.

## 6. View navigation and filtering

The active view has a local search field. Filtering is presentation-only and does not modify the canonical ViewModel.

Keyboard shortcut:

```text
Ctrl/Cmd + K
```

Counts in navigation are derived from the current Studio snapshot. When a filter is active, the active-view count shows visible items versus filterable items.

## 7. Source editor behavior

The source editor adds:

- synchronized line numbers,
- line and character count,
- two-space Tab insertion,
- clickable diagnostics,
- source navigation from cards, rows, graph nodes, and obligations.

The editor remains a plain text editor. Syntax highlighting, completion, and structural editing are separate future capabilities and should not be approximated with an independent source parser in the browser.

## 8. Appearance

The visual system uses semantic theme variables rather than hard-coded per-view colors.

- dark and light themes,
- restrained surfaces and borders,
- consistent state colors for ready, error, capability, resource, runtime, and trusted obligations,
- responsive card grids,
- readable code surfaces,
- visible keyboard focus.

Theme, editor width, editor visibility, and active view are browser-local presentation preferences. They are not project configuration and do not alter Glyph source or compiler output.

## 9. Generated-code usability

Generated Rust, Host scaffold, Manual code, and typed design use a common code surface with a copy action. `manual.rs` ownership is unchanged:

- base `GlyphStudio` never creates or overwrites `manual.rs`,
- `GlyphProjectStudio` creates the initial scaffold when absent,
- subsequent contents remain user-owned.

## 10. Watcher and preview interaction

The file watcher initializes its observed digest from the current disk file. An unsaved preview therefore remains active until the file actually changes, rather than being immediately replaced by the watcher's first polling iteration.

## 11. Acceptance conditions

- Preview compiles unsaved source without changing the source file.
- Reload restores the disk source after a preview.
- The watcher does not replace a preview when the disk file is unchanged.
- Existing Studio views remain available.
- View groups, filtering, resizing, editor toggle, theme toggle, and keyboard shortcuts are present.
- Diagnostics navigate to source lines when a line can be identified.
- JavaScript passes `node --check`.
- Python tests, Glyph 0.4 stabilization, legacy compatibility, Rust tests, demos, and Clippy pass.

## 12. Non-goals

This change does not implement:

- a browser-side Glyph parser,
- syntax highlighting or language-server completion,
- source edits generated from diagrams,
- runtime execution or simulation,
- live runtime event streaming,
- collaborative editing,
- project-wide multi-file navigation.
