from __future__ import annotations


_MARKER = "glyph-direct-io-layout-v1"


_STYLE = r"""
<style id="glyph-direct-io-layout-v1-style">
/* I/Oは参照IDや接続ラベルへ縮約せず、component内へ契約を直接書く。 */
.graph-node .port-title{display:none}
.graph-node .port{align-items:flex-start;margin:5px 0}
.graph-node .port-dot{display:none}
.graph-node .port-text{
  overflow:visible;
  text-overflow:clip;
  white-space:normal;
  overflow-wrap:anywhere;
  word-break:break-word;
  line-height:1.45;
}
.graph-node .io-direction{
  display:inline-block;
  flex:0 0 27px;
  color:var(--faint);
  font:800 9px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.08em;
}
.graph-node .port.out .io-direction{color:var(--green)}
.graph-node .unknown.io-direct{
  white-space:normal;
  overflow-wrap:anywhere;
  font:10px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;
}
</style>
"""


_SCRIPT = r"""
<script id="glyph-direct-io-layout-v1-script">
(() => {
  const MARKER = "glyph-direct-io-layout-v1";
  let timer = null;

  function directRow(row, direction) {
    if (row.dataset.ioDirect === "true") return;
    row.dataset.ioDirect = "true";
    row.querySelector(".port-dot")?.remove();
    const marker = document.createElement("span");
    marker.className = "io-direction";
    marker.textContent = direction;
    row.insertBefore(marker, row.firstChild);
  }

  function directUnknown(element, direction) {
    if (element.dataset.ioDirect === "true") return;
    element.dataset.ioDirect = "true";
    element.classList.add("io-direct");
    const current = element.textContent?.trim() || "undeclared";
    element.textContent = `${direction} ${current}`;
  }

  function enhance() {
    const firstNode = document.querySelector(".graph-node");
    const stage = firstNode?.closest(".graph-stage");
    if (!stage) return;

    /* system構文はport対応を宣言しないため、線には意味を捏造しない。 */
    stage.querySelectorAll(".edge-label").forEach(label => {
      if (label.textContent?.trim() === "connects") label.remove();
    });

    stage.querySelectorAll(".graph-node").forEach(node => {
      const groups = [...node.querySelectorAll(".port-group")];
      groups.forEach((group, index) => {
        const direction = index === 0 ? "IN" : "OUT";
        group.querySelectorAll(".port").forEach(row => directRow(row, direction));
        group.querySelectorAll(".unknown").forEach(row => directUnknown(row, direction));
      });
    });

    stage.dataset.ioContractReady = "true";
    document.dispatchEvent(new CustomEvent("glyph-direct-io-ready", {
      detail: {marker: MARKER},
    }));
  }

  new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(enhance, 0);
  }).observe(document.body, {childList: true, subtree: true});

  setInterval(enhance, 400);
})();
</script>
"""


def enhance_direct_io_html(html: str) -> str:
    """I/O図から抽象的な接続ラベルを除き、型契約を全文表示する。"""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
