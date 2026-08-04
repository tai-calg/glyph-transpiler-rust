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

### Tracked save acknowledgement

`保存して描画` / `Save & Render` first submits the exact editor buffer together with a client-generated save request identifier.

```text
POST /api/save
  request_id
  source
  base_digest
```

The synchronous server path performs only:

```text
validate request_id
  -> detect duplicate request
  -> compare observed base_digest with current disk digest
  -> atomic source write when the content differs
  -> publish status=compiling and operation_id
  -> HTTP 202 Accepted
```

Preprocessing, compilation, diagram construction, layout, and artifact generation do not run in the save HTTP handler.

`request_id` makes the save submission idempotent:

- repeating the same `request_id`, source, and `base_digest` returns the existing operation,
- reusing the identifier for different content returns `save_request_mismatch`,
- a timed-out request can be retried without performing an ambiguous second write.

The server keeps the operation result as one of:

```text
saving
accepted
conflict
error
```

The browser can query it through:

```text
GET /api/save-status/<request_id>
```

A network timeout therefore does not become an unknown final result. The browser continues tracking or resubmits the same idempotent request until the operation reaches a recorded result. The editor, Save button, and Save shortcut remain available; later saves are queued against the latest buffer.

### Background compilation

A single server-side worker performs the heavy pipeline.

```text
saved source
  -> raw macro preprocessing
  -> parse / type check
  -> IR generation
  -> view construction and layout
  -> serialize operation-specific temporary artifact
  -> verify current operation and server state
  -> atomically publish artifact
  -> status=ready or status=error
```

Only one compilation runs at a time. If another save occurs during compilation, the newest pending source replaces older pending work. A completed result is published only when its `operation_id` still matches the current saved source.

Artifact JSON serialization and temporary-file writing occur outside the shared snapshot lock. The worker then briefly acquires the lock, verifies that the operation is still current and the server is not stopping, renames the temporary artifact, and publishes the matching snapshot. An obsolete or stopped operation discards its temporary artifact.

Expected compiler and artifact errors become structured diagnostics. An unexpected worker exception becomes `internal_compile_error`; it does not leave the snapshot permanently in `Compiling`, and the worker continues processing later requests.

The existing `IncrementalCompiler` provides exact-content caching. This workflow does not claim edit-range or syntax-tree incremental compilation; responsiveness comes from separating persistence from background computation.

Keyboard shortcut:

```text
Ctrl/Cmd + S
```

The shortcut is ignored while an IME composition is active.

A save request captures the exact submitted source. If the user edits while save confirmation is running, the newer editor buffer remains `Unsaved`. Repeated save shortcuts are serialized on the client and converge on the latest editor buffer.

Saving a clean source that already matches a `ready` or `compiling` snapshot is a no-op. It does not rewrite the file, create a new diagram version, or restart compilation. An `error` snapshot may be retried with the same source.

### Lightweight compilation polling

Active compilation is observed through:

```text
GET /api/status
```

This response contains only version, status, digests, operation identifier, update time, and diagnostic count. It does not contain source text, full diagnostics, or diagram views.

The browser fetches full `/api/state` only when needed:

- initial application load,
- a clean external source change,
- a transition from `compiling` to `ready` or `error`,
- explicit external-version loading.

This avoids serializing and transferring the entire diagram model four times per second during a long compilation.

### External file changes

Every editor session keeps the digest of the disk source from which it started editing. `/api/save` sends that value as `base_digest`.

```text
base_digest == observed current disk digest
  -> continue save

base_digest != observed current disk digest
  -> HTTP 409 save_conflict
```

When the editor is clean, an external save updates both the editor and the compiled snapshot. When the editor is dirty, Studio keeps the local buffer and opens an explicit conflict dialog:

- `外部版を読み込む` / `Load external version`
- `自分の版で上書き` / `Overwrite with mine`
- `キャンセル` / `Cancel`

Overwrite resubmits the local source using the external digest displayed in the conflict dialog. If the external file changes again before the request reaches the server's digest check, the server returns another 409 and the newer external version must be reviewed.

This is observed-revision conflict detection, not a cross-process filesystem transaction. An unrelated editor does not participate in Glyph Studio's lock, so a very small race remains between reading the file revision and replacing it. The UI and documentation must not describe this as strict filesystem compare-and-swap.

Cancelling the dialog preserves `Conflict`. The Conflict indicator remains keyboard- and pointer-accessible so the resolution dialog can be reopened. Failure to reload the external version preserves both the local buffer and the unresolved conflict.

### Leaving or stopping

Closing or reloading the window while the editor is unsaved, conflicted, or awaiting save confirmation invokes the browser's unsaved-change confirmation. A clean saved editor does not trigger the confirmation.

When the application stops, it serializes shutdown with source persistence, marks the server as stopping, clears pending compilation, changes an unfinished snapshot from `Compiling` to `server_stopping`, and rejects publication from an already running operation. A late worker result cannot replace the artifact or snapshot after shutdown has started. Operation-specific and fixed atomic-write temporary files are removed on shutdown and again at the next startup after an abnormal process exit.

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
Confirming save
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

`Confirming save` covers source-write result tracking. `Compiling` begins after the source is known to be on disk. Compilation diagnostics are shown directly under the editor and in the current view. Diagnostics with a source line navigate to that line.

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

A source file saved outside Glyph Studio enters the same background compilation worker as `Save & Render`. Browser status polling compares the returned disk digest with the editor's `base_digest`:

- clean editor: fetch and adopt the external source and snapshot,
- dirty editor: fetch the external source, preserve the local buffer, and enter `Conflict`,
- unchanged digest: do not fetch full views, rerender, or replace editor text.

The watcher does not enqueue a duplicate build for a digest already published as `compiling` by the application save path.

The public Desktop API does not expose `/api/preview`. The only source-changing compile path is `/api/save`; `/api/rebuild` queues compilation of the file already present on disk.

## 11. Structured errors

Source persistence failures are separate from compiler diagnostics. The server returns structured error codes such as:

```text
source_read_permission_denied
source_read_failed
save_permission_denied
save_no_space
save_io_error
server_stopping
save_request_mismatch
invalid_save_request_id
```

Compilation and publication may report:

```text
compile_error
internal_compile_error
artifact_write_failed
artifact_publish_failed
```

If persistence fails, the source file is not reported as saved and no compile operation is queued.

## 12. Acceptance conditions

- Typing does not change the active compiled snapshot or diagram version.
- The delivered HTML contains no compile button, `/api/preview` request, preview timer, preview controller, or Ctrl/Cmd+Enter compile shortcut.
- `保存して描画` / `Save & Render` and Ctrl/Cmd+S submit an idempotent `request_id`, source, and base digest.
- A duplicate request ID with identical content returns the existing save operation; different content returns `save_request_mismatch`.
- `/api/save-status/<request_id>` resolves a timed-out save as saving, accepted, conflict, or error.
- `/api/save` does not wait for heavy compilation.
- `/api/status` remains responsive during deliberately slow compilation and artifact serialization and does not return source or full views.
- A saved snapshot exposes `status=compiling` and an `operation_id` before the final result.
- A newer save prevents an older in-flight compilation or temporary artifact from publishing stale views.
- Artifact serialization and temporary-file writing do not hold the shared snapshot lock.
- An unexpected view or layout exception becomes `internal_compile_error`; the worker remains alive and accepts a later valid save.
- An edit made during save confirmation remains unsaved.
- Repeated Ctrl/Cmd+S requests converge on the latest editor buffer.
- Saving an unchanged clean source is a no-op while its snapshot is ready or compiling.
- A macro changed through `/api/save` is reprocessed before the final diagram snapshot is published.
- A syntax error can be saved, reported, retried, corrected, and successfully rebuilt.
- A compiling or failed source preserves the last valid views and exposes a visible stale banner.
- A clean external save updates the editor and rendered snapshot.
- A dirty external save produces HTTP 409 and requires explicit load or observed-revision overwrite resolution.
- An additional external change before overwrite produces another 409 rather than being destroyed.
- Cancelling or failing external reload keeps the local buffer and Conflict state.
- Persistence I/O failures return structured errors and leave the existing source unchanged.
- Stopping during compilation prevents late artifact and snapshot publication and leaves no operation temporary file.
- Closing or reloading with unsaved, conflicted, or save-pending content invokes `beforeunload` protection.
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
- strict cross-process filesystem compare-and-swap,
- a browser-side Glyph parser,
- syntax highlighting or language-server completion,
- source edits generated from diagrams,
- runtime execution or simulation,
- live runtime event streaming,
- collaborative editing,
- automatic three-way merging,
- project-wide multi-file navigation.
