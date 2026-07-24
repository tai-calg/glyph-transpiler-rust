from __future__ import annotations


_MARKER = "glyph-failure-result-labels-v1"


_SCRIPT = r"""
<script id="glyph-failure-result-labels-v1-script">
(() => {
  const MARKER = "glyph-failure-result-labels-v1";
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

  function withPipe(value, transition) {
    const text = String(value ?? "");
    const failureType = String(transition?.failure_type ?? "").trim();
    if (!transition?.synthesized_failure || !failureType) return text;
    const suffix = ` ! ${failureType}`;
    return text.endsWith(suffix)
      ? `${text.slice(0, -suffix.length)} | ${failureType}`
      : text;
  }

  function setTextIfChanged(element, value) {
    if (!element || element.textContent === value) return false;
    element.textContent = value;
    return true;
  }

  async function applyFailureResultLabels() {
    if (running) return;
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    if (!stage || stage.dataset.transitionInputActionLabelsReady !== "true") return;
    running = true;
    try {
      const machine = await readMachine();
      if (!machine) return;

      (machine.transitions || []).forEach((transition, index) => {
        if (!transition.synthesized_failure || !transition.failure_type) return;
        const id = `T${index + 1}`;
        const action = withPipe(transition.action, transition);
        const display = withPipe(transition.display_label, transition);

        const compact = stage.querySelector(`.transition-label[data-transition-id="${id}"]`);
        if (compact?.classList.contains("input-action-label")) {
          const next = withPipe(compact.textContent, transition);
          setTextIfChanged(compact, next);
          compact.dataset.inputActionLabel = next;
        }

        const detailId = document.querySelector(
          `.transition-detail[data-transition-id="${id}"] .transition-detail-id.input-action-label`,
        );
        if (detailId) {
          const next = withPipe(detailId.textContent, transition);
          setTextIfChanged(detailId, next);
          detailId.dataset.inputActionLabel = next;
        }

        const semantic = document.querySelector(
          `.transition-detail[data-transition-id="${id}"] .transition-detail-uml`,
        );
        if (semantic && semantic.dataset.failureResultDisplay !== display) {
          const outcome = semantic.querySelector(".transition-detail-outcome")?.outerHTML || "";
          semantic.innerHTML = `${escapeHtml(display)}${outcome}`;
          semantic.dataset.failureResult = transition.failure_type;
          semantic.dataset.failureResultDisplay = display;
        }

        if (compact) {
          compact.title = display;
          compact.dataset.fullLabel = display;
          compact.dataset.failureAction = action;
        }
      });

      stage.dataset.failureResultNotationReady = "true";
      document.dispatchEvent(new CustomEvent("glyph-failure-result-labels-ready", {
        detail: {machine: machine.name, marker: MARKER},
      }));
    } finally {
      running = false;
    }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(() => applyFailureResultLabels().catch(error => {
      console.error("failure result label rendering failed", error);
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


def enhance_failure_result_html(html: str) -> str:
    """Render synthesized effect failures with Glyph's `| ErrorType` notation.

    The compiler-derived transition still retains `failure_type` and
    `synthesized_failure` as separate structured fields. This layer only replaces
    the earlier display-only `! ErrorType` suffix in visible full and compact
    labels, matching the source declaration `SuccessType|ErrorType`.
    """

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
