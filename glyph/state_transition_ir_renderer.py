from __future__ import annotations


_MARKER = "glyph-state-transition-ir-v2-renderer"


_SCRIPT = r"""
<script id="glyph-state-transition-ir-v2-renderer-script">
(() => {
  const MARKER = "glyph-state-transition-ir-v2-renderer";
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
    return text(transition?.condition_raw ?? transition?.condition) || "otherwise";
  }

  function actionOf(transition) {
    const action = text(transition?.action) || "—";
    const failure = text(transition?.failure_type);
    return failure ? `${action} | ${failure}` : action;
  }

  function summaryOf(transition) {
    return `${inputOf(transition)}➡︎${actionOf(transition)}`;
  }

  function signatureOf(machine) {
    return [
      machine?.name || "",
      machine?.transition_ir?.version || "",
      ...(machine?.transitions || []).map(transition => [
        transition.id ?? "",
        transition.event ?? "",
        transition.guard ?? "",
        transition.action ?? "",
        transition.failure_type ?? "",
        transition.display_label ?? "",
      ].join("\u001f")),
    ].join("\u001e");
  }

  async function render() {
    if (running) return;
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    if (!stage || stage.dataset.transitionInputActionLabelsReady !== "true") return;
    running = true;
    try {
      const machine = await readMachine();
      if (!machine || Number(machine?.transition_ir?.version) !== 2) return;
      const signature = signatureOf(machine);
      let changed = stage.dataset.stateTransitionIRV2Labels !== signature;

      (machine.transitions || []).forEach((transition, index) => {
        const id = transition.id || `T${index + 1}`;
        const summary = summaryOf(transition);
        const compact = stage.querySelector(`.transition-label[data-transition-id="${id}"]`);
        if (compact?.classList.contains("compact") && compact.textContent !== summary) {
          compact.textContent = summary;
          compact.dataset.inputActionLabel = summary;
          changed = true;
        }
        const detailId = document.querySelector(
          `.transition-detail[data-transition-id="${id}"] .transition-detail-id.input-action-label`,
        );
        if (detailId && detailId.textContent !== summary) {
          detailId.textContent = summary;
          detailId.dataset.inputActionLabel = summary;
          changed = true;
        }
        if (compact) {
          compact.title = text(transition.display_label);
          compact.dataset.fullLabel = text(transition.display_label);
        }
      });

      stage.dataset.stateTransitionIRV2Labels = signature;
      stage.dataset.stateTransitionIRV2LabelsReady = "true";
      // Compatibility signal for existing browser tests and third-party themes.
      stage.dataset.failureResultNotationReady = "true";
      if (changed) {
        document.dispatchEvent(new CustomEvent("glyph-state-transition-ir-v2-labels-ready", {
          detail: {machine: machine.name, marker: MARKER},
        }));
      }
    } finally {
      running = false;
    }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(() => render().catch(error => {
      console.error("StateTransitionIR v2 rendering failed", error);
    }), 0);
  }

  document.addEventListener("glyph-transition-input-action-labels-ready", schedule);
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


def enhance_state_transition_ir_html(html: str) -> str:
    """Render v2 transition summaries from structured fields only."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
