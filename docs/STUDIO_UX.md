# Glyph Studio UX

## 1. Objective

Glyph Studio is a design workspace, not only a generated-file viewer. The interface keeps three activities visible and distinct:

1. edit Glyph source,
2. save and compile the design,
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

### Edit

Typing changes only the editor buffer and its presentation state.

```text
editor input
  -> mark Unsaved
  -> update line numbers and lightweight editor presentation
```

Typing does not invoke the preprocessor, parser, type checker, IR builders, diagram layout, or browser rendering. There is no debounced compile preview and no compile-on-keystroke path.

### Save and render

`Save & Render` atomically writes the editor contents to the source file and rebuilds the Studio snapshot.

```text
editor text
    ↓ POST /api/save
atomic source write
    ↓
raw macro preprocessing
    ↓
parse / type check / IR generation
    ↓
Studio snapshot and diagram rendering
```

Keyboard shortcut:

```text
Ctrl/Cmd + S
```

Saving is the only editor action that starts compilation and diagram rendering. A compilation error does not undo a successful source-file write.

### Reload

`Reload` discards the current editor contents and rebuilds from the file on disk. When the editor is dirty, the UI asks before discarding changes.

### External file changes

The file watcher rebuilds only after the source file on disk changes. This supports saves made by an external editor without reintroducing compile-on-keystroke behavior inside Glyph Studio.

## 4. State communication

The interface separates persistence and compilation state.

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
busy: saving / reloading / external-file rebuild
```

Compilation diagnostics are shown directly under the editor and in the current view. Diagnostics with a source line navigate to that line.

When compilation fails, the saved source remains on disk. The viewer may retain the last valid diagram, but it must not present that diagram as the result of the invalid source.

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
- source navigation from cards, rows, graph nodes, and obligations,
- exact identifier occurrence highlighting.

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

## 10. Watcher interaction

The file watcher initializes its observed digest from the current disk file. Unsaved editor contents are not compilation input and are not replaced unless the user explicitly reloads or the disk file actually changes.

A source file saved outside Glyph Studio enters the same preprocessing and compilation pipeline as `Save & Render`.

## 11. Acceptance conditions

- Typing does not change the active compiled snapshot or diagram version.
- The delivered HTML contains no compile button, `/api/preview` request, preview timer, or Ctrl/Cmd+Enter compile shortcut.
- Save and Ctrl/Cmd+S write the source before preprocessing, compilation, and diagram rendering.
- A macro changed through `/api/save` is reprocessed before the new diagram snapshot is published.
- A syntax error can be saved, reported, corrected, and successfully rebuilt.
- An external file save is detected and rebuilt through the same compilation pipeline.
- Reload restores the disk source.
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
