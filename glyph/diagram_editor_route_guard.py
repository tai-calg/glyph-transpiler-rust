from __future__ import annotations


_MARKER = "glyph-diagram-editor-route-guard-v1"

_SCRIPT = r"""
<script id="glyph-diagram-editor-route-guard-v1-script">
(() => {
  let repairing = false;
  function verify() {
    if (repairing) return;
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    if (!stage || stage.dataset.initialRouteReady !== "true") return;
    const raw = stage.querySelector(":scope > svg.edge-svg > path:not(.state-transition-path)");
    const routed = stage.querySelector(":scope > svg.edge-svg > path.initial-transition-path");
    if (!raw || routed) return;
    repairing = true;
    delete stage.dataset.initialRouteReady;
    delete stage.dataset.initialTransitionRouting;
    queueMicrotask(() => {
      document.dispatchEvent(new CustomEvent("glyph-transition-input-action-labels-ready"));
      repairing = false;
    });
  }
  document.addEventListener("glyph-initial-transition-route-ready", verify);
  document.addEventListener("change", event => {
    if (event.target?.id === "machine-select") verify();
  });
  new MutationObserver(verify).observe(document.getElementById("view") || document.body, {
    attributes: true,
    attributeFilter: ["class", "data-initial-route-ready", "data-initial-transition-routing"],
    childList: true,
    subtree: true,
  });
  verify();
})();
</script>
"""


def enhance_diagram_editor_route_guard_html(html: str) -> str:
    """Re-run initial routing only when its DOM and readiness flag disagree."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
