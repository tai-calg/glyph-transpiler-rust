from __future__ import annotations


_MARKER = "glyph-layout-shelf-viewport-sync-v1"


_SCRIPT = r"""
<script id="glyph-layout-shelf-viewport-sync-v1-script">
(() => {
  const MARKER = "glyph-layout-shelf-viewport-sync-v1";
  const MIN_SCALE = .25;
  const MAX_SCALE = 3;
  const FIT_MARGIN = 32;

  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));
  const roundScale = value => Math.round(clamp(value, MIN_SCALE, MAX_SCALE) * 100) / 100;

  function nextPaint() {
    return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }

  function diagramIdentity(stage) {
    const tab = document.querySelector(".tab.active")?.dataset.tab || "state";
    const index = tab === "state"
      ? document.getElementById("machine-select")?.value || 0
      : document.getElementById("system-select")?.value || 0;
    return `${stage.dataset.diagramDigest || "source"}:${tab}:${index}`;
  }

  function stageSize(stage) {
    const styledWidth = Number.parseFloat(stage.style.width || "0") || 0;
    const styledHeight = Number.parseFloat(stage.style.height || "0") || 0;
    return {
      width: Math.max(1, styledWidth, stage.scrollWidth),
      height: Math.max(1, styledHeight, stage.scrollHeight),
    };
  }

  function surfaceFor(shell, stage) {
    if (stage.parentElement?.classList.contains("glyph-zoom-surface")) {
      return stage.parentElement;
    }
    const surface = document.createElement("div");
    surface.className = "glyph-zoom-surface";
    shell.insertBefore(surface, stage);
    surface.appendChild(stage);
    return surface;
  }

  async function silentFit(stage) {
    const shell = stage.closest(".canvas-shell");
    if (!shell) {
      const error = Error("diagram canvas is unavailable after shelf repair");
      error.code = "layout-shelf-viewport-unavailable";
      throw error;
    }
    const size = stageSize(stage);
    const availableWidth = Math.max(80, shell.clientWidth - FIT_MARGIN * 2);
    const availableHeight = Math.max(80, shell.clientHeight - FIT_MARGIN * 2);
    const scale = roundScale(Math.min(
      availableWidth / size.width,
      availableHeight / size.height,
    ));
    const surface = surfaceFor(shell, stage);
    stage.style.transform = `scale(${scale})`;
    stage.dataset.viewportScale = String(scale);
    surface.style.width = `${Math.ceil(size.width * scale)}px`;
    surface.style.height = `${Math.ceil(size.height * scale)}px`;
    surface.dataset.viewportScale = String(scale);

    const identity = diagramIdentity(stage);
    sessionStorage.setItem(`glyph.diagram.viewport-scale.v1:${identity}`, String(scale));
    sessionStorage.setItem(`glyph.diagram.viewport-mode.v1:${identity}`, "fit");
    const control = document.getElementById("diagram-zoom-value");
    if (control) control.textContent = `${Math.round(scale * 100)}%`;

    await nextPaint();
    shell.scrollLeft = Math.max(
      0,
      surface.offsetLeft + size.width * scale / 2 - shell.clientWidth / 2,
    );
    shell.scrollTop = Math.max(
      0,
      surface.offsetTop + size.height * scale / 2 - shell.clientHeight / 2,
    );
    shell.dispatchEvent(new Event("scroll"));
    await nextPaint();
    return scale;
  }

  async function refitShelf(stage) {
    const viewport = window.glyphDiagramViewport;
    if (!viewport || viewport.version < 2 || typeof viewport.mode !== "function") {
      const error = Error("diagram viewport is unavailable after shelf repair");
      error.code = "layout-shelf-viewport-unavailable";
      throw error;
    }
    const mode = viewport.mode();
    if (mode && mode !== "fit") {
      stage.dataset.layoutShelfViewportState = `preserved:${mode}`;
      return {refitted: false, mode};
    }
    const scale = await silentFit(stage);
    stage.dataset.layoutShelfViewportState = "fit";
    stage.dataset.layoutShelfViewportScale = String(scale);
    document.dispatchEvent(new CustomEvent("glyph-layout-shelf-viewport-ready", {
      detail: {marker: MARKER, mode: "fit", scale},
    }));
    return {refitted: true, mode: "fit", scale};
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
    """Refit shelf geometry without scheduling a second layout generation."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
