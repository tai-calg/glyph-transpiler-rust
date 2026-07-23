from __future__ import annotations


_MARKER = "glyph-transition-input-action-labels-v2"


_STYLE = r"""
<style id="glyph-transition-input-action-labels-v2-style">
.edge-label.transition-label.compact.input-action-label{
  min-width:0;
  max-width:260px;
  border-radius:7px;
  padding:3px 7px;
  white-space:normal;
  overflow-wrap:anywhere;
  letter-spacing:0;
  font-weight:750;
}
.transition-detail-id.input-action-label{
  width:max-content;
  max-width:270px;
  padding:3px 7px;
  border-radius:7px;
  overflow-wrap:anywhere;
  text-align:center;
}
</style>
"""


_SCRIPT = r"""
<script id="glyph-transition-input-action-labels-v2-script">
(() => {
  const MARKER = "glyph-transition-input-action-labels-v2";
  let running = false;
  let timer = null;

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

  function text(value) {
    return String(value ?? "").trim();
  }

  function inputOf(transition) {
    const event = text(transition?.event);
    const guard = text(transition?.guard);
    if (event && guard) return `${event} [${guard}]`;
    if (event) return event;
    if (guard) return `[${guard}]`;

    const raw = text(transition?.condition_raw ?? transition?.condition);
    return raw || "otherwise";
  }

  function actionOf(transition) {
    return text(transition?.action) || "—";
  }

  function inputActionOf(transition) {
    return `${inputOf(transition)}→${actionOf(transition)}`;
  }

  function signatureOf(machine) {
    return [
      machine?.name || "",
      ...(machine?.transitions || []).map(transition => [
        transition.source_state,
        transition.target_state,
        transition.event ?? "",
        transition.guard ?? "",
        transition.action ?? "",
        transition.condition_raw ?? transition.condition ?? "",
      ].join("\u001f")),
    ].join("\u001e");
  }

  async function applyInputActionLabels() {
    if (running) return;
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    if (!stage || stage.dataset.labelLayoutReady !== "true") return;
    running = true;
    try {
      const machine = await readMachine();
      if (!machine) return;
      const signature = signatureOf(machine);
      if (stage.dataset.transitionInputActionLabels === signature) return;
      stage.dataset.transitionInputActionLabels = signature;

      (machine.transitions || []).forEach((transition, index) => {
        const internalId = `T${index + 1}`;
        const summary = inputActionOf(transition);
        const label = stage.querySelector(`.transition-label[data-transition-id="${internalId}"]`);
        if (label?.classList.contains("compact")) {
          label.textContent = summary;
          label.classList.add("input-action-label");
          label.dataset.inputActionLabel = summary;
        }
        const detailId = document.querySelector(
          `.transition-detail[data-transition-id="${internalId}"] .transition-detail-id`,
        );
        if (detailId) {
          detailId.textContent = summary;
          detailId.classList.add("input-action-label");
          detailId.dataset.inputActionLabel = summary;
        }
      });

      stage.dataset.transitionInputActionLabelsReady = "true";
      document.dispatchEvent(new CustomEvent("glyph-transition-input-action-labels-ready", {
        detail: {machine: machine.name, marker: MARKER},
      }));
    } finally {
      running = false;
    }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(() => applyInputActionLabels().catch(() => {}), 0);
  }

  document.addEventListener("glyph-transition-layout-ready", schedule);
  document.addEventListener("glyph-uml-transition-ready", schedule);
  document.addEventListener("change", event => {
    if (event.target?.id === "machine-select") schedule();
  });
  const root = document.getElementById("view") || document.body;
  new MutationObserver(schedule).observe(root, {childList: true, subtree: true});
  schedule();
})();
</script>
"""


def enhance_transition_route_html(html: str) -> str:
    """Replace compact internal T identifiers with `input→action` summaries.

    T identifiers remain internal correlation keys for hover/focus behavior. Short
    UML `event [guard] / action` labels remain unchanged. Only labels compacted by
    the collision-avoidance layer are replaced visually, while full semantics stay
    available in the transition details table.
    """

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
