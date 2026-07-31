from __future__ import annotations


_MARKER = "glyph-transition-label-drag-guard-v2"

_SCRIPT = r"""
<script id="glyph-transition-label-drag-guard-v2-script">
(()=>{
const MARKER="glyph-transition-label-drag-guard-v2";
if(window.glyphTransitionLabelDragGuard?.marker===MARKER)return;

// Compatibility-only capability marker. Pointer ownership, movement thresholds,
// constraint projection, persistence, and reset are exclusively implemented by
// glyphTransitionLayoutInteractionAdapter v4 or newer.
window.glyphTransitionLabelDragGuard=Object.freeze({
  marker:MARKER,
  version:2,
  interactionOwner:"glyph-transition-layout-interaction-adapter-v4",
  ownsPointerEvents:false,
  ownsPersistence:false,
});
})();
</script>
"""


def enhance_transition_label_drag_guard_html(html: str) -> str:
    """Expose a passive compatibility marker for the unified interaction owner."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
