from __future__ import annotations


_MARKER = "glyph-state-node-interaction-layer-v1"

_STYLE = r"""
<style id="glyph-state-node-interaction-layer-v1-style">
/*
 * Transition labels and enabling-case clusters may geometrically cross a state
 * node.  The node remains the primary direct-manipulation target, so keep it on
 * a stable interaction layer above those derived annotations.
 */
.graph-stage .state-node{
  z-index:20;
  pointer-events:auto;
}
.graph-stage .state-node.selected-node,
.graph-stage .state-node.dragging{
  z-index:21;
}
.graph-stage .initial-dot{
  z-index:22;
  pointer-events:none;
}
</style>
"""


def enhance_state_node_interaction_layer_html(html: str) -> str:
    """Keep state nodes hit-testable when transition annotations overlap them."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>")
