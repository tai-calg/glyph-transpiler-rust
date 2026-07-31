from __future__ import annotations


_MARKER = "glyph-layout-dependency-bridge-v1"


_SCRIPT = r"""
<script id="glyph-layout-dependency-bridge-v1-script">
(() => {
  const MARKER = "glyph-layout-dependency-bridge-v1";

  function claimTransactionOwnership() {
    const control = window.glyphTransitionLegacyControl;
    const transaction = window.glyphTransitionLayoutTransaction;
    if (!control || transaction?.ownsScheduling !== true) return false;
    control.ownsScheduling = true;
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    if (stage) stage.dataset.transitionLayoutOwner = transaction.marker || "transaction";
    return true;
  }

  document.addEventListener("glyph-layout-local-repair-ready", () => {
    window.glyphInitialTransitionRouter?.schedule?.("layout-local-repair", 0);
  });
  document.addEventListener("glyph-transition-layout-transaction-ready", claimTransactionOwnership);
  claimTransactionOwnership();

  window.glyphLayoutDependencyBridge = Object.freeze({
    marker: MARKER,
    version: 2,
    claimTransactionOwnership,
  });
})();
</script>
"""


def enhance_layout_dependency_bridge_html(html: str) -> str:
    """Reconnect certificates and disable legacy layout schedulers."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
