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

### Save acknowledgement

`保存して描画` / `Save & Render` first persists the exact editor buffer. The HTTP request does not wait for preprocessing, compilation, layout, or rendering.

```text
editor text
  -> POST /api/save
  -> compare base_digest with disk digest
  -> atomic source write
  -> publish status=compiling and operation_id
  -> HTTP 202 Accepted
```

The source is therefore either:

- not written and accompanied by a structured HTTP error, or
- durably written before the accepted response is returned.

The browser remains interactive after the short save acknowledgement. It polls `/api/state` while the background operation is active.

### Background compilation

A single server-side worker performs the heavy pipeline.

```text
saved source
  -> raw macro preprocessing
  -> parse / type check
  -> IR generation
  -> view construction and layout
  -> artifact write
  -> status=ready or status=error
```

Only one compilation runs at a time. If another save occurs during compilation, the newest pending source replaces older pending work. A completed result is published only when its `operation_id` still matches the current saved source. An obsolete compilation can finish internally but cannot replace the current Studio snapshot or generated views.

The existing `IncrementalCompiler` provides exact-content caching. This workflow does not claim edit-range or syntax-tree incremental compilation; responsiveness comes from separating persistence from background computation.

Keyboard shortcut:

```text
Ctrl/Cmd + S
```

The shortcut is ignored while an IME composition is active.

A save request captures the exact submitted source. If the user edits while the save acknowledgement is running, the newer editor buffer remains `Unsaved`. Repeated save shortcuts are serialized on the client and converge on the latest editor buffer.

### Save-result reconciliation

Save acknowledgement has a short transport timeout. A timeout does not immediately mean that saving failed: the browser queries `/api/state` and compares the server source with the exact submitted buffer.

```text
submitted source == server source
  -> save confirmed; continue polling operation_id

submitted source != server source or state unavailable
  -> keep editor Unsaved and report that the outcome is unconfirmed
```

The browser never reports a timed-out save as failed while silently treating its source as saved.

### External file changes

Every editor session keeps the digest of the disk source from which it started editing. `/api/save` sends that value as `base_digest`.

```text
base_digest == current disk digest
  -> save

base_digest != current disk digest
  -> HTTP 409 save_conflict
```

When the editor is clean, an external save updates both the editor and the compiled snapshot. When the editor is dirty, Studio keeps the local buffer and opens an explicit conflict dialog:

- `外部版を読み込む` / `Load external version`
- `自分の版で上書き` / `Overwrite with mine`
- `キャンセル` / `Cancel`

Overwrite is compare-and-swap, not an unconditional force operation. It resubmits the local source using the digest displayed in the conflict dialog. If the external file changes again before the overwrite reaches the server, the server returns another 409 and the newer external version must be reviewed.

Cancelling the dialog preserves `Conflict`. The Conflict indicator remains keyboard- and pointer-accessible so the resolution dialog can be reopened. Failure to reload the external version preserves both the local buffer and the unresolved conflict.

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
Saving
Compiling
Compile error
```

The header displays both values, for example:

```text
Unsaved · Rendered
Saved · Compiling
Saved · Compile error
Conflict · Rendered
```

`Saving` covers only the source-write acknowledgement. `Compiling` begins after the source is known to be on disk. The Save button is disabled only during the short acknowledgement, not during background compilation.

Compilation diagnostics are shown directly under the editor and in the current view. Diagnostics with a source line navigate to that line.

When compilation succeeds:

```text
source digest == rendered digest
```

When a saved source is compiling or fails to compile, the last successful views remain available. The snapshot exposes:

```text
digest
rendered_digest
last_successful_version
operation_id
```

If `digest != rendered_digest`, the viewer displays a persistent stale banner. During compilation it states that the new saved source is compiling and that the diagram still represents the previous successful source. After failure it states that the diagram is the last successfully compiled result. The old diagram is never presented as the result of the new source.

## 5. Workspace layout

Desktop layout:

```text
source editor | draggable splitter | navigation | active view
```

The editor width is resizable and remembered locally. The editor can be hidden to give diagrams and generated output the full workspace.

On narrow windows, persistence state remains visible in a compact form rather than disappearing completely.

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

## 8. Appearance and accessibility

The visual system uses semantic theme variables rather than hard-coded per-view colors.

- dark and light themes,
- restrained surfaces and borders,
- consistent state colors for ready, error, capability, resource, runtime, and trusted obligations,
- responsive card grids,
- readable code surfaces,
- visible keyboard focus.

Save state uses an `aria-live` region. The stale banner is a status region. Compilation errors are alerts. The conflict dialog has labelled title and description elements, and Conflict can be reopened with pointer, Enter, or Space.

Theme, editor width, editor visibility, and active view are browser-local presentation preferences. They are not project configuration and do not alter Glyph source or compiler output.

## 9. Generated-code usability

Generated Rust, Host scaffold, Manual code, and typed design use a common code surface with a copy action. `manual.rs` ownership is unchanged:

- base `GlyphStudio` never creates or overwrites `manual.rs`,
- `GlyphProjectStudio` creates the initial scaffold when absent,
- subsequent contents remain user-owned.

## 10. Watcher interaction

The file watcher initializes its observed digest from the current disk file. Unsaved editor contents are not compilation input.

A source file saved outside Glyph Studio enters the same background compilation worker as `Save & Render`. Browser polling compares the returned disk digest with the editor's `base_digest`:

- clean editor: adopt the external source and snapshot,
- dirty editor: preserve the local buffer and enter `Conflict`,
- unchanged digest: do not rerender or replace editor text.

The watcher does not enqueue a duplicate build for a digest already published as `compiling` by the application save path.

The public Desktop API does not expose `/api/preview`. The only source-changing compile path is `/api/save`; `/api/rebuild` queues compilation of the file already present on disk.

## 11. Structured persistence errors

Source persistence failures are separate from compiler diagnostics. The server returns structured error codes such as:

```text
source_read_permission_denied
source_read_failed
save_permission_denied
save_no_space
save_io_error
```

If persistence fails, the source file is not reported as saved and no compile operation is queued.

## 12. Acceptance conditions

- Typing does not change the active compiled snapshot or diagram version.
- The delivered HTML contains no compile button, `/api/preview` request, preview timer, preview controller, or Ctrl/Cmd+Enter compile shortcut.
- `保存して描画` / `Save & Render` and Ctrl/Cmd+S atomically write the source and receive HTTP 202 without waiting for heavy compilation.
- `/api/state` remains responsive during a deliberately slow compilation.
- A saved snapshot exposes `status=compiling` and an `operation_id` before the final result.
- A newer save prevents an older in-flight compilation from publishing stale views.
- An edit made during save acknowledgement remains unsaved.
- Repeated Ctrl/Cmd+S requests converge on the latest editor buffer.
- A macro changed through `/api/save` is reprocessed before the final diagram snapshot is published.
- A syntax error can be saved, reported, corrected, and successfully rebuilt.
- A compiling or failed source preserves the last valid views and exposes a visible stale banner.
- A clean external save updates the editor and rendered snapshot.
- A dirty external save produces HTTP 409 and requires explicit load or compare-and-swap overwrite resolution.
- An additional external change before overwrite produces another 409 rather than being destroyed.
- Cancelling or failing external reload keeps the local buffer and Conflict state.
- Persistence I/O failures return structured errors and leave the existing source unchanged.
- Closing or reloading with unsaved or conflicted content invokes `beforeunload` protection.
- Save shortcuts do not fire during IME composition.
- Existing Studio views remain available.
- View groups, filtering, resizing, editor toggle, theme toggle, and keyboard shortcuts are present.
- Diagnostics navigate to source lines when a line can be identified.
- JavaScript passes `node --check`.
- Python tests, Glyph 0.4 stabilization, legacy compatibility, Rust tests, demos, and Clippy pass.

## 13. Non-goals

This change does not implement:

- edit-range or AST-node incremental compilation,
- cancellation inside a currently executing compiler call,
- a browser-side Glyph parser,
- syntax highlighting or language-server completion,
- source edits generated from diagrams,
- runtime execution or simulation,
- live runtime event streaming,
- collaborative editing,
- automatic three-way merging,
- project-wide multi-file navigation.
