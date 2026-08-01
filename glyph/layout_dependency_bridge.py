from __future__ import annotations


_MARKER = "glyph-layout-dependency-bridge-v1"


_STYLE = r"""
<style id="glyph-layout-dependency-bridge-v1-style">
.graph-stage[data-transition-layout-published-once="true"][data-transition-layout-state="pending"] .transition-io-cluster,
.graph-stage[data-transition-layout-published-once="true"][data-transition-publication-ready="false"] .transition-io-cluster{
  visibility:visible!important;
  pointer-events:auto!important;
}
</style>
"""


_SCRIPT = r"""
<script id="glyph-layout-dependency-bridge-v1-script">
(() => {
  const MARKER = "glyph-layout-dependency-bridge-v1";

  function stageOf() {
    return document.querySelector(".state-node")?.closest(".graph-stage") || null;
  }

  function claimTransactionOwnership() {
    const control = window.glyphTransitionLegacyControl;
    const transaction = window.glyphTransitionLayoutTransaction;
    if (!control || transaction?.ownsScheduling !== true) return false;
    control.ownsScheduling = true;
    const stage = stageOf();
    if (stage) stage.dataset.transitionLayoutOwner = transaction.marker || "transaction";
    return true;
  }

  function markPublishedLayout() {
    const stage = stageOf();
    if (!stage) return false;
    stage.dataset.transitionLayoutPublishedOnce = "true";
    stage.dataset.transitionLayoutPublishedGeneration = String(
      stage.dataset.transitionLayoutGeneration || "0"
    );
    return true;
  }

  document.addEventListener("glyph-layout-local-repair-ready", () => {
    window.glyphInitialTransitionRouter?.schedule?.("layout-local-repair", 0);
  });
  document.addEventListener("glyph-transition-layout-transaction-ready", claimTransactionOwnership);
  document.addEventListener("glyph-layout-publication-certificate-ready", markPublishedLayout);
  claimTransactionOwnership();

  window.glyphLayoutDependencyBridge = Object.freeze({
    marker: MARKER,
    version: 3,
    claimTransactionOwnership,
    markPublishedLayout,
  });
})();
</script>
"""


def enhance_layout_dependency_bridge_html(html: str) -> str:
    """Reconnect certificates and preserve the last published layout atomically."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
