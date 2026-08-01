from __future__ import annotations


_MARKER = "glyph-transition-layout-transaction-bootstrap-v1"

_SCRIPT = r"""
<script id="glyph-transition-layout-transaction-bootstrap-v1-script">
(()=>{
const MARKER="glyph-transition-layout-transaction-bootstrap-v1";
const control={
  marker:MARKER,
  version:4,
  ownsScheduling:true,
  protocol:"ordinary-layout-v1",
  managedScripts:new Set(),
};
control.request=(reason="bootstrap-request")=>
  window.glyphTransitionLayoutTransaction?.schedule?.(reason,0)??0;
window.glyphTransitionLegacyControl=control;
})();
</script>
"""


def enhance_transition_layout_transaction_bootstrap_html(html: str) -> str:
    """Expose the lightweight layout owner without monkey-patching browser APIs."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
