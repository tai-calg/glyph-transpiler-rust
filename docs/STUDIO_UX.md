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

`保存して描画` / `Save & Render` atomically writes the editor contents to the source file and rebuilds the Studio snapshot.

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

A save request captures the exact submitted source. If the user edits while that request is running, the newer editor buffer remains `Unsaved` after the submitted version completes. Repeated save shortcuts are serialized, and only the latest pending editor buffer is retained for the next request.

### External file changes

Every editor session keeps the digest of the disk source from which it started editing. `/api/save` sends that value as `base_digest`.

```text
base_digest == current disk digest
  -> save

base_digest != current disk digest
  -> HTTP 409 save_conflict
```

When the editor is clean, an external save updates both the editor and the rendered snapshot. When the editor is dirty, Studio keeps the local buffer and opens an explicit conflict dialog:

- `外部版を読み込む` / `Load external version`
- `自分の版で上書き` / `Overwrite with mine`
- `キャンセル` / `Cancel`

No external change is silently overwritten. Forced overwrite is available only through the explicit conflict action.

### Leaving the page

Closing or reloading the window while the editor is unsaved or conflicted invokes the browser's unsaved-change confirmation. A clean saved editor does not trigger the confirmation.

## 4. State communication

Persistence and compilation are independent state axes.

### Persistence state

```text
Saved
Unsaved
Conflict
```

### Render state

```text
Rendered
Saving & rendering
Compile error
```

The header displays both values, for example:

```text
Unsaved · Rendered
Saved · Compile error
Conflict · Rendered
```

Compilation diagnostics are shown directly under the editor and in the current view. Diagnostics with a source line navigate to that line.

When compilation succeeds:

```text
source digest == rendered digest
```

When a saved source fails to compile, the source remains on disk while the last successful views remain available. The snapshot therefore exposes separate fields:

```text
digest
rendered_digest
last_successful_version
```

If `digest != rendered_digest`, the viewer displays a persistent stale banner stating that the diagram belongs to the last successfully compiled saved source. The old diagram is never presented as the result of the invalid source.

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

The file watcher initializes its observed digest from the current disk file. Unsaved editor contents are not compilation input.

A source file saved outside Glyph Studio enters the same preprocessing and compilation pipeline as `Save & Render`. Browser polling then compares the returned disk digest with the editor's `base_digest`:

- clean editor: adopt the external source and snapshot,
- dirty editor: preserve the local buffer and enter `Conflict`,
- unchanged digest: do not rerender or replace editor text.

The public Desktop API does not expose `/api/preview`. The only source-changing compile path is `/api/save`; `/api/rebuild` recompiles the file already present on disk.

## 11. Acceptance conditions

- Typing does not change the active compiled snapshot or diagram version.
- The delivered HTML contains no compile button, `/api/preview` request, preview timer, preview controller, or Ctrl/Cmd+Enter compile shortcut.
- `保存して描画` / `Save & Render` and Ctrl/Cmd+S write the source before preprocessing, compilation, and diagram rendering.
- An edit made during an active save remains unsaved after the submitted source completes.
- Repeated Ctrl/Cmd+S requests are serialized and converge on the latest editor buffer.
- A macro changed through `/api/save` is reprocessed before the new diagram snapshot is published.
- A syntax error can be saved, reported, corrected, and successfully rebuilt.
- A failed compilation preserves the last valid views and exposes a visible stale banner.
- A clean external save updates the editor and rendered snapshot.
- A dirty external save produces HTTP 409 on normal save and requires explicit load or overwrite resolution.
- Closing or reloading with unsaved or conflicted content invokes `beforeunload` protection.
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
- automatic three-way merging,
- project-wide multi-file navigation.
