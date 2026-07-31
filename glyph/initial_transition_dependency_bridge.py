from __future__ import annotations


_MARKER = "glyph-initial-transition-dependency-bridge-v1"


_SCRIPT = r"""
<script id="glyph-initial-transition-dependency-bridge-v1-script">
(() => {
  const MARKER = "glyph-initial-transition-dependency-bridge-v1";
  if (window.glyphInitialTransitionDependencyBridge?.marker === MARKER) return;

  let observedSvg = null;
  let routeObserver = null;
  let viewObserver = null;
  let bindTimer = null;
  let destroyed = false;
  let lastSignature = "";

  function currentSvg() {
    return document.querySelector(".graph-stage > svg.edge-svg");
  }

  function normalPaths(svg) {
    return [...(svg?.querySelectorAll(":scope > path.state-transition-path") || [])];
  }

  function geometrySignature(svg) {
    return normalPaths(svg).map((path, index) => [
      index,
      path.dataset.transitionId || "",
      path.getAttribute("class") || "",
      path.getAttribute("d") || "",
      path.getAttribute("transform") || "",
    ].join("\u001e")).join("\u001f");
  }

  function hasNormalPath(node) {
    return node?.nodeType === 1 && (
      node.matches?.("path.state-transition-path")
      || Boolean(node.querySelector?.("path.state-transition-path"))
    );
  }

  function classPreviouslyMarked(record) {
    return record.attributeName === "class"
      && String(record.oldValue || "").split(/\s+/).includes("state-transition-path");
  }

  function relevantMutation(record) {
    if (record.type === "attributes") {
      const target = record.target;
      return target?.nodeType === 1
        && target.tagName?.toLowerCase() === "path"
        && (target.matches?.(".state-transition-path") || classPreviouslyMarked(record));
    }
    if (record.type === "childList") {
      return [...record.addedNodes, ...record.removedNodes].some(hasNormalPath);
    }
    return false;
  }

  function invalidateIfChanged(reason) {
    if (destroyed) return false;
    const svg = currentSvg();
    if (!svg) {
      scheduleBind();
      return false;
    }
    if (svg !== observedSvg) bind();
    const next = geometrySignature(svg);
    if (next === lastSignature) return false;
    lastSignature = next;
    const router = window.glyphInitialTransitionRouter;
    if (!router || router.version < 2) return false;
    router.schedule(reason, 0);
    return true;
  }

  function bind() {
    if (destroyed) return;
    clearTimeout(bindTimer);
    bindTimer = null;
    const svg = currentSvg();
    if (svg === observedSvg) return;
    routeObserver?.disconnect();
    routeObserver = null;
    observedSvg = svg;
    lastSignature = geometrySignature(svg);
    if (!svg) return;
    routeObserver = new MutationObserver(records => {
      if (!records.some(relevantMutation)) return;
      queueMicrotask(() => invalidateIfChanged("normal-route-geometry-changed"));
    });
    routeObserver.observe(svg, {
      attributes: true,
      attributeOldValue: true,
      attributeFilter: ["class", "d", "transform"],
      childList: true,
      subtree: true,
    });
  }

  function scheduleBind() {
    if (destroyed) return;
    clearTimeout(bindTimer);
    bindTimer = setTimeout(bind, 0);
  }

  for (const eventName of [
    "glyph-diagram-geometry-kernel-ready",
    "glyph-uml-transition-ready",
    "glyph-transition-layout-transaction-ready",
  ]) {
    document.addEventListener(eventName, scheduleBind);
  }
  document.addEventListener("change", event => {
    if (event.target?.id === "machine-select") scheduleBind();
  });

  const view = document.getElementById("view") || document.body;
  viewObserver = new MutationObserver(records => {
    if (records.some(record => [...record.addedNodes, ...record.removedNodes].some(node => (
      node?.nodeType === 1 && (
        node.matches?.(".graph-stage,svg.edge-svg")
        || node.querySelector?.(".graph-stage,svg.edge-svg")
      )
    )))) scheduleBind();
  });
  viewObserver.observe(view, {childList: true, subtree: true});

  for (const eventName of ["pagehide", "beforeunload"]) {
    window.addEventListener(eventName, () => {
      destroyed = true;
      clearTimeout(bindTimer);
      routeObserver?.disconnect();
      viewObserver?.disconnect();
    }, {once: true});
  }

  window.glyphInitialTransitionDependencyBridge = Object.freeze({
    marker: MARKER,
    version: 1,
    bind,
    invalidateIfChanged,
    get signature() { return lastSignature; },
  });
  scheduleBind();
})();
</script>
"""


def enhance_initial_transition_dependency_bridge_html(html: str) -> str:
    """Invalidate an initial-route certificate when normal route geometry changes."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
