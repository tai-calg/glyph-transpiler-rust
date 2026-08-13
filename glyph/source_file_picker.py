from __future__ import annotations

import os
from pathlib import Path


_PICKER_MARKER = 'data-glyph-source-file-picker="1"'


class SourceSelectionError(ValueError):
    """A requested GUI source path is outside the allowed picker root."""


def find_source_picker_root(source_path: str | Path) -> Path:
    """Prefer the repository examples directory, then fall back to the source folder."""

    source = Path(source_path).resolve()
    configured = os.environ.get("GLYPH_EXAMPLES_DIR")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(Path.cwd() / "examples")
    for parent in (source.parent, *source.parents):
        candidates.append(parent / "examples")

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_dir():
            return resolved
    return source.parent


def source_file_catalog(root: str | Path, current_path: str | Path) -> dict[str, object]:
    root_path = Path(root).resolve()
    current = Path(current_path).resolve()
    files = [
        {
            "path": path.relative_to(root_path).as_posix(),
            "label": path.relative_to(root_path).as_posix(),
        }
        for path in sorted(root_path.rglob("*.glyph"))
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(root_path).parts)
    ]
    try:
        current_relative: str | None = current.relative_to(root_path).as_posix()
    except ValueError:
        current_relative = None
    return {
        "root": str(root_path),
        "current": current_relative,
        "current_path": str(current),
        "files": files,
    }


def resolve_source_selection(root: str | Path, selected: object) -> Path:
    if not isinstance(selected, str) or not selected.strip():
        raise SourceSelectionError("source path must be a non-empty relative path")
    relative = Path(selected)
    if relative.is_absolute():
        raise SourceSelectionError("source path must be relative to the picker root")

    root_path = Path(root).resolve()
    candidate = (root_path / relative).resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise SourceSelectionError("source path escapes the picker root") from exc
    if candidate.suffix.lower() != ".glyph":
        raise SourceSelectionError("source file must use the .glyph extension")
    if not candidate.is_file():
        raise SourceSelectionError(f"Glyph source does not exist: {candidate}")
    return candidate


def enhance_source_file_picker_html(html: str) -> str:
    """Add an examples-first source selector to the shared Studio header."""

    if _PICKER_MARKER in html:
        return html

    status_anchor = '<div class="status" id="status">'
    picker = (
        '<label class="source-file-picker" '
        + _PICKER_MARKER
        + '><span>File</span><select id="source-file-select" '
        'aria-label="Glyph source file"><option value="">Loading…</option></select></label>'
    )
    if status_anchor not in html:
        raise ValueError("source file picker requires the Studio status anchor")
    html = html.replace(status_anchor, picker + status_anchor, 1)

    style = r'''
<style data-glyph-source-file-picker-style="1">
.source-file-picker{display:flex;align-items:center;gap:6px;min-width:0;color:var(--muted);font-size:11px}
.source-file-picker span{white-space:nowrap}
.source-file-picker select{width:min(260px,24vw);padding:6px 28px 6px 8px;font:12px ui-monospace,SFMono-Regular,Menlo,monospace;overflow:hidden;text-overflow:ellipsis}
.source-file-picker select:disabled{opacity:.55}
@media(max-width:980px){.source-file-picker span{display:none}.source-file-picker select{width:180px}}
</style>
'''
    script = r'''
<script data-glyph-source-file-picker-script="1">
(() => {
  const picker = document.getElementById('source-file-select');
  if (!picker) return;

  const requestJson = async (path, options = {}) => {
    const response = await fetch(path, {
      headers: {'Content-Type': 'application/json'},
      ...options,
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.message || payload.error || `HTTP ${response.status}`);
    return payload;
  };

  const currentEditorIsDirty = () => {
    const sourceEditor = document.getElementById('editor');
    try {
      return Boolean(sourceEditor && typeof snapshot !== 'undefined' && snapshot && sourceEditor.value !== (snapshot.source || ''));
    } catch (_) {
      return false;
    }
  };

  const refresh = async () => {
    picker.disabled = true;
    try {
      const catalog = await requestJson('/api/source-files');
      picker.replaceChildren();
      if (!catalog.current) {
        const current = document.createElement('option');
        current.value = '';
        current.textContent = `Current: ${catalog.current_path || '(outside examples)'}`;
        current.selected = true;
        picker.appendChild(current);
      }
      for (const file of catalog.files || []) {
        const option = document.createElement('option');
        option.value = file.path;
        option.textContent = file.label;
        option.selected = file.path === catalog.current;
        picker.appendChild(option);
      }
      picker.dataset.current = catalog.current || '';
      picker.title = `Source root: ${catalog.root || ''}`;
      picker.disabled = false;
    } catch (error) {
      picker.replaceChildren();
      const option = document.createElement('option');
      option.textContent = 'File list unavailable';
      picker.appendChild(option);
      picker.title = String(error);
      picker.disabled = true;
    }
  };

  picker.addEventListener('change', async () => {
    const selected = picker.value;
    const previous = picker.dataset.current || '';
    if (!selected || selected === previous) return;
    if (currentEditorIsDirty() && !window.confirm('Unsaved editor changes will be discarded. Open another Glyph file?')) {
      picker.value = previous;
      return;
    }
    picker.disabled = true;
    try {
      await requestJson('/api/open-source', {
        method: 'POST',
        body: JSON.stringify({path: selected}),
      });
      window.location.reload();
    } catch (error) {
      picker.disabled = false;
      picker.value = previous;
      window.alert(`Could not open Glyph source: ${error}`);
    }
  });

  refresh();
})();
</script>
'''
    return html.replace("</head>", style + "</head>", 1).replace("</body>", script + "</body>", 1)
