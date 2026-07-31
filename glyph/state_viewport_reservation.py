from __future__ import annotations


_MARKER = "glyph-state-viewport-reservation-v1"

_STYLE = r"""
<style id="glyph-state-viewport-reservation-v1-style">
.analysis-panel{
  max-height:min(220px,28dvh);
  overflow:auto;
  overscroll-behavior:contain;
  scrollbar-gutter:stable;
}
.analysis-panel>.analysis-title{
  position:sticky;
  top:0;
  z-index:2;
  background:var(--panel);
}
.canvas-shell[data-state-viewport-reserved="true"]{
  overflow:auto!important;
  overscroll-behavior:contain;
  scrollbar-gutter:stable;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-state-viewport-reservation-v1-script">
(() => {
  const MARKER = "glyph-state-viewport-reservation-v1";
  const BOTTOM_MARGIN = 16;
  const MIN_VISIBLE_HEIGHT = 240;
  const PREFERRED_MIN_HEIGHT = 390;
  let frame = 0;
  let observedShell = null;
  let shellObserver = null;
  let destroyed = false;

  function activeStateShell() {
    if (document.querySelector(".tab.active")?.dataset.tab !== "state") return null;
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return stage?.closest(".canvas-shell") || null;
  }

  function reserve(reason = "scheduled") {
    if (destroyed) return;
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      const shell = activeStateShell();
      if (!shell || destroyed) return;
      const rect = shell.getBoundingClientRect();
      const visibleTop = Math.max(0, rect.top);
      const available = Math.max(
        MIN_VISIBLE_HEIGHT,
        Math.floor(window.innerHeight - visibleTop - BOTTOM_MARGIN),
      );
      const minimum = Math.min(PREFERRED_MIN_HEIGHT, available);
      const height = `${available}px`;
      const minHeight = `${minimum}px`;
      if (shell.style.height !== height) shell.style.height = height;
      if (shell.style.maxHeight !== height) shell.style.maxHeight = height;
      if (shell.style.minHeight !== minHeight) shell.style.minHeight = minHeight;
      shell.dataset.stateViewportReserved = "true";
      shell.dataset.stateViewportHeight = String(available);
      shell.dataset.stateViewportReason = reason;
    });
  }

  function bindShell() {
    const shell = activeStateShell();
    if (shell === observedShell) return;
    shellObserver?.disconnect();
    observedShell = shell;
    shellObserver = null;
    if (shell && typeof ResizeObserver === "function") {
      shellObserver = new ResizeObserver(() => reserve("canvas-shell-resize"));
      shellObserver.observe(shell);
    }
    reserve("state-shell-change");
  }

  for (const eventName of [
    "glyph-transition-layout-transaction-ready",
    "glyph-layout-publication-certificate-ready",
    "glyph-layout-shelf-viewport-ready",
    "glyph-layout-compact-shelf-repair-ready",
    "glyph-layout-shelf-repair-ready",
    "glyph-locale-changed",
  ]) {
    document.addEventListener(eventName, () => {
      bindShell();
      reserve(eventName);
    });
  }

  document.addEventListener("click", event => {
    if (event.target?.closest?.('.tab[data-tab="state"]')) {
      requestAnimationFrame(() => {
        bindShell();
        reserve("state-tab-selected");
      });
    }
  });
  document.addEventListener("change", event => {
    if (event.target?.matches?.("#machine-select")) {
      requestAnimationFrame(() => {
        bindShell();
        reserve("machine-change");
      });
    }
  });

  new MutationObserver(() => {
    bindShell();
    reserve("view-mutation");
  }).observe(document.getElementById("view") || document.body, {
    childList: true,
    subtree: true,
  });
  window.addEventListener("resize", () => reserve("window-resize"));
  for (const eventName of ["pagehide", "beforeunload"]) {
    window.addEventListener(eventName, () => {
      destroyed = true;
      cancelAnimationFrame(frame);
      shellObserver?.disconnect();
    }, {once: true});
  }

  window.glyphStateViewportReservation = {
    marker: MARKER,
    version: 1,
    reserve,
    audit: () => {
      const shell = activeStateShell();
      if (!shell) return {ok: false, reason: "inactive-state-view"};
      const rect = shell.getBoundingClientRect();
      const visibleBottom = Math.min(window.innerHeight, rect.bottom);
      const visibleHeight = Math.max(0, visibleBottom - Math.max(0, rect.top));
      return {
        ok: shell.dataset.stateViewportReserved === "true"
          && visibleHeight >= Math.min(MIN_VISIBLE_HEIGHT, shell.clientHeight),
        visibleHeight,
        clientHeight: shell.clientHeight,
        reservedHeight: Number(shell.dataset.stateViewportHeight || 0),
      };
    },
  };

  bindShell();
  reserve("bootstrap");
})();
</script>
"""


def enhance_state_viewport_reservation_html(html: str) -> str:
    """Reserve browser-visible height for State diagrams and scroll diagnostics."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
