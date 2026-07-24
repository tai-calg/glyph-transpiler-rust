from __future__ import annotations


_MARKER = "glyph-uml-transition-semantics-v1"


_STYLE = r"""
<style id="glyph-uml-transition-semantics-v1-style">
.state-transition-path.failure-transition{
  stroke:var(--red)!important;
  stroke-dasharray:7 5;
}
.transition-label.failure-transition{
  border-color:rgba(255,122,139,.8)!important;
  color:#ffd4da!important;
  background:#321923!important;
}
.transition-detail.failure-transition{
  border-left:3px solid var(--red);
  background:rgba(255,122,139,.045);
}
.transition-detail-uml{
  grid-column:3/4;
  color:var(--text);
  font:11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
  overflow-wrap:anywhere;
  word-break:break-word;
}
.transition-detail-outcome{
  display:inline-flex;
  align-items:center;
  width:max-content;
  margin-top:4px;
  border:1px solid var(--line);
  border-radius:999px;
  padding:2px 6px;
  color:var(--muted);
  font-size:9px;
  text-transform:uppercase;
  letter-spacing:.07em;
}
.transition-detail-outcome.failure{
  color:var(--red);
  border-color:rgba(255,122,139,.5);
}
.transition-detail-outcome.success{
  color:var(--green);
  border-color:rgba(69,209,154,.5);
}
.transition-detail-condition{
  display:none;
}
@media(max-width:1100px){
  .transition-detail-uml{grid-column:2/4}
}
</style>
"""


_SCRIPT = r"""
<script id="glyph-uml-transition-semantics-v1-script">
(() => {
  const MARKER = "glyph-uml-transition-semantics-v1";
  let running = false;
  let timer = null;

  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
  })[character]);

  function selectedMachine(state) {
    const machines = state?.views?.state?.machines || [];
    const selected = document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;
    return machines.find(machine => machine.name === selected) || machines[0] || null;
  }

  async function readMachine() {
    const response = await fetch("/api/state", {cache: "no-store"});
    if (!response.ok) return null;
    return selectedMachine(await response.json());
  }

  function semanticSignature(machine) {
    return [
      machine?.name || "",
      ...(machine?.transitions || []).map(transition => [
        transition.source_state,
        transition.target_state,
        transition.display_label,
        transition.outcome,
        transition.failure_type,
      ].join("\u001f")),
    ].join("\u001e");
  }

  function outcomeMarkup(outcome) {
    if (!outcome || outcome === "normal") return "";
    return `<span class="transition-detail-outcome ${escapeHtml(outcome)}">${escapeHtml(outcome)}</span>`;
  }

  async function enhance() {
    if (running) return;
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    if (!stage || stage.dataset.labelLayoutReady !== "true") return;
    running = true;
    try {
      const machine = await readMachine();
      if (!machine) return;
      const signature = semanticSignature(machine);
      if (stage.dataset.umlTransitionSemantics === signature) return;
      stage.dataset.umlTransitionSemantics = signature;

      const transitions = machine.transitions || [];
      const labels = [...stage.querySelectorAll(".edge-label.transition-label")];
      const paths = [...stage.querySelectorAll(":scope > svg.edge-svg > path.state-transition-path")];
      const details = [...document.querySelectorAll(".transition-detail")];

      transitions.forEach((transition, index) => {
        const id = `T${index + 1}`;
        const display = String(transition.display_label ?? transition.condition ?? "");
        const label = labels[index];
        const path = paths[index];
        const detail = details[index];
        const failure = transition.outcome === "failure";

        if (label) {
          label.title = display;
          label.dataset.fullLabel = display;
          if (label.dataset.compact !== "true") {
            if (display.length > 30) {
              label.textContent = id;
              label.classList.add("compact");
              label.dataset.compact = "true";
            } else {
              label.textContent = display;
            }
          }
          label.classList.toggle("failure-transition", failure);
        }
        if (path) path.classList.toggle("failure-transition", failure);
        if (detail) {
          detail.classList.toggle("failure-transition", failure);
          detail.querySelectorAll(".transition-detail-uml").forEach(item => item.remove());
          const semantic = document.createElement("span");
          semantic.className = "transition-detail-uml";
          semantic.innerHTML = `${escapeHtml(display || "(unlabeled)")}${outcomeMarkup(transition.outcome)}`;
          const line = detail.querySelector(".transition-detail-line");
          detail.insertBefore(semantic, line || null);
        }
      });

      stage.dataset.umlTransitionReady = "true";
      document.dispatchEvent(new CustomEvent("glyph-uml-transition-ready", {
        detail: {machine: machine.name, transitions: transitions.length},
      }));
    } finally {
      running = false;
    }
  }

  document.addEventListener("glyph-transition-layout-ready", () => {
    clearTimeout(timer);
    timer = setTimeout(() => enhance().catch(() => {}), 0);
  });
  new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(() => enhance().catch(() => {}), 30);
  }).observe(document.body, {childList: true, subtree: true});
  setInterval(() => enhance().catch(() => {}), 450);
})();
</script>
"""


def enhance_uml_transition_html(html: str) -> str:
    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
