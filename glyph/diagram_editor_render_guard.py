from __future__ import annotations


_MARKER = "glyph-diagram-editor-render-guard-v1"

_SCRIPT = r"""
<script id="glyph-diagram-editor-render-guard-v1-script">
(() => {
  let dragging = false;
  let deferred = false;
  const originalRender = window.render;
  if (typeof originalRender === "function") {
    window.render = function guardedRender(...arguments_) {
      if (dragging) {
        deferred = true;
        return;
      }
      return originalRender.apply(this, arguments_);
    };
  }
  document.addEventListener("pointerdown", event => {
    if (event.target?.closest?.(".graph-stage.editable .state-node,.graph-stage.editable .graph-node")) {
      dragging = true;
      deferred = false;
    }
  }, true);
  function release() {
    if (!dragging) return;
    dragging = false;
    if (deferred && typeof window.render === "function") {
      deferred = false;
      queueMicrotask(() => window.render());
    }
  }
  document.addEventListener("pointerup", release, true);
  document.addEventListener("pointercancel", release, true);
})();
</script>
"""


def enhance_diagram_editor_render_guard_html(html: str) -> str:
    """Prevent periodic application refresh from replacing nodes during drag."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
