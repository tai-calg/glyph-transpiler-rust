from __future__ import annotations


_MARKER = "glyph-checked-system-context-ui-v2"

_SCRIPT = r"""
<script id="glyph-checked-system-context-ui-v2-script">
(() => {
  const MARKER = "glyph-checked-system-context-ui-v2";

  function selectedSystem() {
    const systems = snapshot?.views?.io?.systems || [];
    return systems[systemIndex] || null;
  }

  function normalizeDeclaredPorts(system) {
    const cards = [...document.querySelectorAll(".canvas-shell .graph-node")];
    const nodes = system?.nodes || [];
    cards.forEach((card, index) => {
      const node = nodes[index];
      if (!node?.declared_io) return;
      const groups = [...card.querySelectorAll(".port-group")];
      if (!(node.inputs || []).length) {
        const emptyInput = groups[0]?.querySelector(".unknown");
        if (emptyInput) emptyInput.textContent = "none";
      }
      if (node.output === null || node.output === undefined) {
        const emptyOutput = groups[1]?.querySelector(".unknown");
        if (emptyOutput) emptyOutput.textContent = "none";
      }
    });
  }

  function enhance() {
    if (activeTab !== "io") return;
    const system = selectedSystem();
    const checked = system?.kind === "checked-system-context";
    const note = document.querySelector(".view-controls .note");
    if (note) {
      note.textContent = checked
        ? "system宣言の境界・データ・戻り値・作用flowを、型付きコード証拠に照らして表示する。call graphとは別のviewである。"
        : system?.kind === "derived-call-graph"
          ? "system宣言がないため、コンパイラの呼出しグラフを表示する。"
          : "境界に接続されていない内部宣言を表示する。";
    }

    const labels = [...document.querySelectorAll(".canvas-shell .edge-label")];
    const edges = system?.edges || [];
    labels.forEach((label, index) => {
      const text = edges[index]?.label || "flow";
      if (label.textContent !== text) label.textContent = text;
      label.title = text;
    });
    normalizeDeclaredPorts(system);

    const current = document.querySelector('[data-system-meta-owner="checked-context"]');
    if (!checked || !system?.entry) {
      current?.remove();
      return;
    }
    const signature = `${system.name}\u001f${system.entry}\u001f${(system.edges || []).length}`;
    if (current?.dataset.systemMetaSignature === signature) return;
    current?.remove();
    const controls = document.querySelector(".view-controls");
    if (!controls) return;
    controls.insertAdjacentHTML(
      "afterend",
      `<div class="machine-meta" data-system-meta-owner="checked-context" ` +
      `data-system-meta-signature="${esc(signature)}">` +
      `<span class="pill">Checked system context</span>` +
      `<span class="pill">Entry: ${esc(system.entry)}</span>` +
      `<span class="pill">Boundary edges: ${(system.edges || []).length}</span>` +
      `</div>`,
    );
  }

  const originalRenderIo = window.renderIo;
  if (typeof originalRenderIo === "function") {
    window.renderIo = function renderCheckedSystemContext(...arguments_) {
      const result = originalRenderIo.apply(this, arguments_);
      enhance();
      return result;
    };
  }

  document.addEventListener("change", event => {
    if (event.target?.id === "system-select") queueMicrotask(enhance);
  });
  enhance();
})();
</script>
"""


def enhance_code_derived_system_html(html: str) -> str:
    """Add checked-System-Context guidance while preserving the public helper name."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
