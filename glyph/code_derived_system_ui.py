from __future__ import annotations


_MARKER = "glyph-executable-system-boundary-ui-v3"

_STYLE = r"""
<style id="glyph-executable-system-boundary-ui-v3-style">
.graph-node.boundary-entry{border-color:var(--blue);box-shadow:0 0 0 2px rgba(88,166,255,.12),0 10px 25px rgba(0,0,0,.22)}
.graph-node.boundary-source{border-color:var(--green);border-style:dashed}
.graph-node.boundary-sink{border-color:var(--purple)}
.graph-node.boundary-internal{border-color:#40516a}
.graph-node .node-kind .boundary-role{font-weight:800}
.graph-node.boundary-entry .boundary-role{color:var(--blue)}
.graph-node.boundary-source .boundary-role{color:var(--green)}
.graph-node.boundary-sink .boundary-role{color:var(--purple)}
</style>
"""

_SCRIPT = r"""
<script id="glyph-executable-system-boundary-ui-v3-script">
(() => {
  const MARKER = "glyph-executable-system-boundary-ui-v3";

  function selectedSystem() {
    const systems = snapshot?.views?.io?.systems || [];
    return systems[systemIndex] || null;
  }

  function normalizeFunctionCards(system) {
    const cards = [...document.querySelectorAll(".canvas-shell .graph-node")];
    const nodes = system?.nodes || [];
    cards.forEach((card, index) => {
      const node = nodes[index];
      if (!node) return;
      const role = node.boundary_role || "";
      card.classList.remove(
        "boundary-entry",
        "boundary-source",
        "boundary-sink",
        "boundary-internal",
      );
      if (role) {
        card.classList.add(`boundary-${role}`);
        card.dataset.boundaryRole = role;
      } else {
        delete card.dataset.boundaryRole;
      }

      const kind = card.querySelector(".node-kind");
      if (kind && role) {
        kind.innerHTML =
          `<span class="boundary-role">${esc(role)}</span>` +
          ` · ${esc(node.kind || "function")}`;
      }

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
    const checked = system?.contract === "executable-function-boundary";
    const note = document.querySelector(".view-controls .note");
    if (note) {
      note.textContent = checked
        ? "entryから実コードを追跡した完全な関数実行境界。矢印はすべて関数呼出しで、値と型は関数シグネチャに表示する。"
        : system?.kind === "derived-call-graph"
          ? "system宣言がないため、コンパイラの関数呼出しグラフを表示する。"
          : "System境界に含まれない宣言を表示する。";
    }

    const labels = [...document.querySelectorAll(".canvas-shell .edge-label")];
    const edges = system?.edges || [];
    labels.forEach((label, index) => {
      const text = edges[index]?.label || "calls";
      if (label.textContent !== text) label.textContent = text;
      label.title = text;
    });
    normalizeFunctionCards(system);

    const current = document.querySelector(
      '[data-system-meta-owner="executable-boundary"]',
    );
    if (!checked || !system?.entry) {
      current?.remove();
      return;
    }
    const sources = system.sources || [];
    const sinks = system.sinks || [];
    const signature = [
      system.name,
      system.entry,
      sources.join(","),
      sinks.join(","),
      (system.edges || []).length,
    ].join("\u001f");
    if (current?.dataset.systemMetaSignature === signature) return;
    current?.remove();
    const controls = document.querySelector(".view-controls");
    if (!controls) return;
    controls.insertAdjacentHTML(
      "afterend",
      `<div class="machine-meta" data-system-meta-owner="executable-boundary" ` +
      `data-system-meta-signature="${esc(signature)}">` +
      `<span class="pill">Executable System boundary</span>` +
      `<span class="pill">Entry: ${esc(system.entry)}</span>` +
      `<span class="pill">Sources: ${sources.length ? esc(sources.join(", ")) : "none"}</span>` +
      `<span class="pill">Sinks: ${sinks.length ? esc(sinks.join(", ")) : "none"}</span>` +
      `<span class="pill">Calls: ${(system.edges || []).length}</span>` +
      `</div>`,
    );
  }

  const originalRenderIo = window.renderIo;
  if (typeof originalRenderIo === "function") {
    window.renderIo = function renderExecutableSystemBoundary(...arguments_) {
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
    """Render the canonical entry/source/sink executable System boundary."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>",
        _SCRIPT + "\n</body>",
    )
