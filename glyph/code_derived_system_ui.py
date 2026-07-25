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
      label.textContent = edges[index]?.label || "calls";
      label.title = label.textContent;
    });

    document.querySelectorAll('[data-system-meta-owner="code-derived"]').forEach(item => item.remove());
    if (!system?.entry) return;
    const controls = document.querySelector(".view-controls");
    if (!controls) return;
    controls.insertAdjacentHTML(
      "afterend",
      `<div class="machine-meta" data-system-meta-owner="code-derived">` +
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
  document.addEventListener("glyph-diagram-render-stable", enhance);
  new MutationObserver(() => queueMicrotask(enhance)).observe(
    document.getElementById("view") || document.body,
    {childList: true, subtree: true},
  );
  enhance();
})();
</script>
"""


def enhance_code_derived_system_html(html: str) -> str:
    """Explain that I/O systems are checked projections of real Glyph calls."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
