from __future__ import annotations


_MARKER = "glyph-code-derived-system-ui-v1"

_SCRIPT = r"""
<script id="glyph-code-derived-system-ui-v1-script">
(() => {
  const MARKER = "glyph-code-derived-system-ui-v1";

  function selectedSystem() {
    const systems = snapshot?.views?.io?.systems || [];
    return systems[systemIndex] || null;
  }

  function enhance() {
    if (activeTab !== "io") return;
    const system = selectedSystem();
    const note = document.querySelector(".view-controls .note");
    if (note) {
      note.textContent = system?.kind === "code-derived-system"
        ? "system entryから実際の関数呼出しを追跡して生成。図だけの未宣言nodeや架空の接続は受理しない。"
        : "system宣言がないため、コンパイラの呼出しグラフを表示する。";
    }

    const labels = [...document.querySelectorAll(".canvas-shell .edge-label")];
    const edges = system?.edges || [];
    labels.forEach((label, index) => {
      const text = edges[index]?.label || "calls";
      if (label.textContent !== text) label.textContent = text;
      label.title = text;
    });

    const current = document.querySelector('[data-system-meta-owner="code-derived"]');
    if (!system?.entry) {
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
      `<div class="machine-meta" data-system-meta-owner="code-derived" ` +
      `data-system-meta-signature="${esc(signature)}">` +
      `<span class="pill">Derived from code</span>` +
      `<span class="pill">Entry: ${esc(system.entry)}</span>` +
      `<span class="pill">Edges: ${(system.edges || []).length}</span>` +
      `</div>`,
    );
  }

  const originalRenderIo = window.renderIo;
  if (typeof originalRenderIo === "function") {
    window.renderIo = function renderCodeDerivedSystem(...arguments_) {
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
    """Explain that I/O systems are checked projections of real Glyph calls."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
