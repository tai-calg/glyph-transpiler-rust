from __future__ import annotations


_MARKER = "glyph-layout-dependency-bridge-v1"


_SCRIPT = r"""
<script id="glyph-layout-dependency-bridge-v1-script">
(() => {
  const MARKER = "glyph-layout-dependency-bridge-v1";
  document.addEventListener("glyph-layout-local-repair-ready", () => {
    window.glyphInitialTransitionRouter?.schedule?.("layout-local-repair", 0);
  });
  window.glyphLayoutDependencyBridge = Object.freeze({marker: MARKER, version: 1});
})();
</script>
"""


def enhance_layout_dependency_bridge_html(html: str) -> str:
    """Reconnect geometry certificates when a dependent layout object moves."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
