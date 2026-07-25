from __future__ import annotations


_MARKER = "glyph-diagram-render-stability-v1"

_STYLE = r"""
<style id="glyph-diagram-render-stability-v1-style">
.canvas-shell.diagram-render-pending{
  position:relative;
}
.canvas-shell.diagram-render-pending > .graph-stage{
  visibility:hidden!important;
}
.canvas-shell.diagram-render-pending::after{
  content:"Rendering adjusted state diagram…";
  position:absolute;
  inset:0;
  display:grid;
  place-items:center;
  color:var(--muted);
  background:var(--panel);
  font-size:12px;
  letter-spacing:.01em;
  pointer-events:none;
}
.canvas-shell.diagram-render-pending + .transition-index{
  visibility:hidden!important;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-render-stability-v1-script">
(() => {
  const MARKER = "glyph-diagram-render-stability-v1";
  const FALLBACK_DELAY = 1600;
  const REQUIRED_FLAGS = [
    "labelLayoutReady",
    "umlTransitionReady",
    "transitionInputActionLabelsReady",
    "stateTransitionIRV2LabelsReady",
  ];
  let lastRenderKey = null;
  let revealGeneration = 0;
  const fallbackTimers = new WeakMap();

  function stateStage() {
    return document.querySelector(".state-node")?.closest(".graph-stage") || null;
  }

  function renderKey() {
    try {
      return JSON.stringify([
        snapshot?.version ?? null,
        snapshot?.digest ?? "",
        snapshot?.status ?? "",
        activeTab,
        systemIndex,
        machineIndex,
      ]);
    } catch {
      return null;
    }
  }

  function initialRouteReady(stage) {
    const raw = stage.querySelector(":scope > svg.edge-svg > path:not(.state-transition-path)");
    if (!raw) return true;
    return stage.dataset.initialRouteReady === "true"
      && raw.classList.contains("initial-transition-path");
  }

  function fullyAdjusted(stage) {
    if (!stage?.querySelector(".state-node")) return true;
    return REQUIRED_FLAGS.every(name => stage.dataset[name] === "true")
      && initialRouteReady(stage);
  }

  function reveal(stage, state = "ready") {
    if (!stage?.isConnected) return;
    const timer = fallbackTimers.get(stage);
    if (timer) clearTimeout(timer);
    fallbackTimers.delete(stage);
    stage.dataset.renderStable = "true";
    stage.dataset.renderStableState = state;
    stage.closest(".canvas-shell")?.classList.remove("diagram-render-pending");
    document.dispatchEvent(new CustomEvent("glyph-diagram-render-stable", {
      detail: {marker: MARKER, state},
    }));
  }

  function settle(stage = stateStage()) {
    if (!stage?.querySelector(".state-node") || !fullyAdjusted(stage)) return;
    const generation = ++revealGeneration;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (generation !== revealGeneration || stage !== stateStage() || !fullyAdjusted(stage)) return;
      reveal(stage);
    }));
  }

  function markPending(stage = stateStage()) {
    if (!stage?.querySelector(".state-node")) return;
    delete stage.dataset.renderStable;
    stage.dataset.renderStableState = "pending";
    stage.closest(".canvas-shell")?.classList.add("diagram-render-pending");
    const previous = fallbackTimers.get(stage);
    if (previous) clearTimeout(previous);
    fallbackTimers.set(stage, setTimeout(() => {
      if (stage.isConnected && stage.dataset.renderStable !== "true") {
        console.warn("state diagram adjustment timed out; revealing conservative fallback");
        reveal(stage, "fallback");
      }
    }, FALLBACK_DELAY));
    settle(stage);
  }

  const originalRender = window.render;
  if (typeof originalRender === "function") {
    window.render = function stableRender(...arguments_) {
      const key = renderKey();
      const hasRenderedView = Boolean(document.getElementById("view")?.childElementCount);
      if (key && key === lastRenderKey && hasRenderedView) {
        if (typeof setStatus === "function") setStatus(snapshot?.status || "starting");
        return;
      }
      if (document.querySelector(".graph-stage .dragging")) {
        return originalRender.apply(this, arguments_);
      }
      const result = originalRender.apply(this, arguments_);
      lastRenderKey = key;
      markPending();
      return result;
    };
  }

  for (const name of ["renderState", "renderIo"]) {
    const original = window[name];
    if (typeof original !== "function") continue;
    window[name] = function stableDirectRender(...arguments_) {
      const result = original.apply(this, arguments_);
      lastRenderKey = renderKey();
      if (name === "renderState") markPending();
      return result;
    };
  }

  for (const eventName of [
    "glyph-transition-layout-ready",
    "glyph-uml-transition-ready",
    "glyph-transition-input-action-labels-ready",
    "glyph-state-transition-ir-v2-labels-ready",
    "glyph-initial-transition-route-ready",
  ]) {
    document.addEventListener(eventName, () => settle());
  }

  const root = document.getElementById("view") || document.body;
  new MutationObserver(records => {
    const stage = stateStage();
    if (!stage) return;
    if (records.some(record => record.type === "childList")) markPending(stage);
    else settle(stage);
  }).observe(root, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: [
      "data-label-layout-ready",
      "data-uml-transition-ready",
      "data-transition-input-action-labels-ready",
      "data-state-transition-ir-v2-labels-ready",
      "data-initial-route-ready",
    ],
  });

  markPending();
})();
</script>
"""


def enhance_diagram_render_stability_html(html: str) -> str:
    """Commit state diagrams only after all browser-side adjustment passes finish.

    The base application polls the compiler snapshot. This layer suppresses a DOM
    rebuild when the rendered snapshot and selected view are unchanged, and hides a
    newly built state graph until label packing, UML semantics, input/action labels,
    StateTransitionIR v2 labels, and initial-route layout have completed. The user
    therefore sees either the previous committed graph or the next fully adjusted
    graph, never an intermediate T-label/raw-route frame.
    """

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
