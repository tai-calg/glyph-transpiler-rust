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
        if path.is_file()
        and not any(
            part.startswith(".")
            for part in path.relative_to(root_path).parts
        )
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
    """Make the existing source-path label open an examples-first file picker."""

    if _PICKER_MARKER in html:
        return html
    if 'id="path"' not in html:
        raise ValueError("source file picker requires the Studio path label")

    menu = r'''
<div id="source-file-menu" class="source-file-menu" hidden data-glyph-source-file-picker="1" role="dialog" aria-label="Glyph source file picker">
  <div class="source-file-menu-title">Open Glyph source</div>
  <select id="source-file-select" aria-label="Glyph source file"><option value="">Loading…</option></select>
  <div class="source-file-menu-root" id="source-file-root">examples/</div>
</div>
'''
    style = r'''
<style data-glyph-source-file-picker-style="1">
#path[data-source-picker-ready="true"]{cursor:pointer}
#path[data-source-picker-ready="true"]:hover{color:var(--text)}
#path[data-source-picker-ready="true"]:focus-visible{outline:2px solid var(--blue);outline-offset:3px;border-radius:3px}
.source-file-menu[hidden]{display:none!important}
.source-file-menu{position:fixed;z-index:1000;width:min(360px,calc(100vw - 16px));padding:10px;border:1px solid var(--line);border-radius:10px;background:var(--panel);box-shadow:var(--shadow)}
.source-file-menu-title{font-weight:700;margin-bottom:8px}
.source-file-menu select{width:100%;min-width:0;font:12px ui-monospace,SFMono-Regular,Menlo,monospace}
.source-file-menu-root{margin-top:7px;color:var(--muted);font:10px ui-monospace,SFMono-Regular,Menlo,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
'''
    script = r'''
<script data-glyph-source-file-picker-script="1">
(() => {
  const trigger = document.getElementById('path');
  const menu = document.getElementById('source-file-menu');
  const picker = document.getElementById('source-file-select');
  const rootLabel = document.getElementById('source-file-root');
  if (!trigger || !menu || !picker || !rootLabel) return;

  trigger.dataset.sourcePickerReady = 'true';
  trigger.setAttribute('role', 'button');
  trigger.setAttribute('tabindex', '0');
  trigger.setAttribute('aria-haspopup', 'dialog');
  trigger.setAttribute('aria-expanded', 'false');
  trigger.title = 'Click to choose a Glyph source file';

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

  const close = () => {
    menu.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
  };

  const position = () => {
    const rect = trigger.getBoundingClientRect();
    const width = Math.min(360, Math.max(240, window.innerWidth - 16));
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
    menu.style.left = `${left}px`;
    menu.style.top = `${Math.min(window.innerHeight - 120, rect.bottom + 7)}px`;
  };

  const refresh = async () => {
    picker.disabled = true;
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
    rootLabel.textContent = catalog.root || 'examples/';
    picker.disabled = false;
  };

  const open = async () => {
    position();
    menu.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    try {
      await refresh();
      picker.focus();
    } catch (error) {
      picker.replaceChildren();
      const option = document.createElement('option');
      option.textContent = 'File list unavailable';
      picker.appendChild(option);
      picker.disabled = true;
      rootLabel.textContent = String(error);
    }
  };

  trigger.addEventListener('click', event => {
    event.stopPropagation();
    if (menu.hidden) open();
    else close();
  });
  trigger.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (menu.hidden) open();
      else close();
    }
  });
  menu.addEventListener('click', event => event.stopPropagation());
  document.addEventListener('click', () => close());
  window.addEventListener('resize', () => { if (!menu.hidden) position(); });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !menu.hidden) {
      close();
      trigger.focus();
    }
  });

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
})();
</script>
'''
    return (
        html.replace("</head>", style + "</head>", 1)
        .replace("</body>", menu + script + "</body>", 1)
    )
