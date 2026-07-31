from __future__ import annotations


_MARKER = "glyph-layout-shelf-viewport-sync-v1"


_SCRIPT = r"""
<script id="glyph-layout-shelf-viewport-sync-v1-script">
(() => {
  const MARKER = "glyph-layout-shelf-viewport-sync-v1";

  function nextPaint() {
    return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }

  async function refitShelf(stage) {
    const viewport = window.glyphDiagramViewport;
    if (!viewport || viewport.version < 2 || typeof viewport.fit !== "function") {
      const error = Error("diagram viewport is unavailable after shelf repair");
      error.code = "layout-shelf-viewport-unavailable";
      throw error;
    }
    const mode = typeof viewport.mode === "function" ? viewport.mode() : "";
    if (mode && mode !== "fit") {
      stage.dataset.layoutShelfViewportState = `preserved:${mode}`;
      return {refitted: false, mode};
    }
    viewport.fit();
    await nextPaint();
    stage.dataset.layoutShelfViewportState = "fit";
    stage.dataset.layoutShelfViewportScale = String(
      Number.parseFloat(stage.dataset.viewportScale || "1") || 1
    );
    document.dispatchEvent(new CustomEvent("glyph-layout-shelf-viewport-ready", {
      detail: {
        marker: MARKER,
        mode: "fit",
        scale: Number(stage.dataset.layoutShelfViewportScale),
      },
    }));
    return {
      refitted: true,
      mode: "fit",
      scale: Number(stage.dataset.layoutShelfViewportScale),
    };
  }

  const base = window.glyphLayoutLocalRepair;
  if (!base || base.version < 5 || typeof base.repair !== "function") {
    console.error("layout shelf viewport sync requires shelf repair v1");
    return;
  }
  const baseRepair = base.repair.bind(base);
  base.repair = async (stage, violations, options = {}) => {
    const result = await baseRepair(stage, violations, options);
    if (!result?.shelfRerouted) return result;
    if (options.cancelled?.()) throw new DOMException("stale shelf viewport fit", "AbortError");
    const viewport = await refitShelf(stage);
    if (options.cancelled?.()) throw new DOMException("stale shelf viewport fit", "AbortError");
    result.metrics = {...(result.metrics || {}), viewport};
    return result;
  };
  base.version = 6;
  base.shelfViewportMarker = MARKER;
})();
</script>
"""


def enhance_layout_shelf_viewport_sync_html(html: str) -> str:
    """Refit publication geometry after a certified shelf expands the stage."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
