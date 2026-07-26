from __future__ import annotations


_MARKER = "glyph-state-transition-ir-v3-renderer"


_STYLE = r"""
<style id="glyph-state-transition-ir-v3-renderer-style">
.transition-label.provisional-trigger,
.edge-label.provisional-trigger{
  border-style:dashed!important;
  border-color:rgba(231,191,98,.82)!important;
  color:var(--amber)!important;
  background:rgba(231,191,98,.10)!important;
}
.transition-detail-id.provisional-trigger{
  border-style:dashed;
  border-color:rgba(231,191,98,.82);
  color:var(--amber);
  background:rgba(231,191,98,.08);
}
.transition-label.unclassified-condition,
.transition-detail-id.unclassified-condition{
  border-style:dotted!important;
  color:var(--amber)!important;
}
.glyph-visually-hidden{
  position:absolute!important;
  width:1px!important;
  height:1px!important;
  padding:0!important;
  margin:-1px!important;
  overflow:hidden!important;
  clip:rect(0,0,0,0)!important;
  white-space:nowrap!important;
  border:0!important;
}
</style>
"""


_SCRIPT = r"""
<script id="glyph-state-transition-ir-v3-renderer-script">
(() => {
  const MARKER = "glyph-state-transition-ir-v3-renderer";
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

  function english() {
    return (window.GlyphI18n?.locale || document.documentElement.lang || "ja").startsWith("en");
  }

  function both(ja, en) {
    return english() ? en : ja;
  }

  function triggerOf(transition) {
    const trigger = transition?.trigger;
    if (trigger && text(trigger.display)) {
      return {
        display: text(trigger.display),
        role: text(trigger.role) || "confirmed-trigger",
        confidence: text(trigger.confidence) || "unknown",
        roots: trigger.provenance_roots || [],
        path: trigger.dataflow_path || [],
      };
    }
    const event = text(transition?.event);
    if (!event) return null;
    return {
      display: event,
      role: event.startsWith("? ") ? "provisional-trigger" : "confirmed-trigger",
      confidence: "legacy",
      roots: [],
      path: [],
    };
  }

  function guardsOf(transition) {
    if (Array.isArray(transition?.guards)) {
      return transition.guards.map(text).filter(Boolean);
    }
    const guard = text(transition?.guard);
    return guard ? [guard] : [];
  }

  function inputOf(transition) {
    const trigger = triggerOf(transition);
    const guards = guardsOf(transition);
    const unknown = (transition?.unclassified_conditions || []).map(text).filter(Boolean);
    let label = "";
    if (trigger) {
      label = `${trigger.role === "provisional-trigger" ? "? " : ""}${trigger.display.replace(/^\?\s*/, "")}`;
    }
    if (guards.length) {
      const guard = guards.join("&");
      label += label ? ` [${guard}]` : `[${guard}]`;
    }
    if (unknown.length) {
      label += label ? ` ? ${unknown.join("&")}` : `? ${unknown.join("&")}`;
    }
    return label || "otherwise";
  }

  function actionOf(transition) {
    const action = text(transition?.action) || "—";
    const failure = text(transition?.failure_type);
    return failure ? `${action} | ${failure}` : action;
  }

  function summaryOf(transition) {
    return `${inputOf(transition)}➡︎${actionOf(transition)}`;
  }

  function evidenceOf(transition) {
    const trigger = triggerOf(transition);
    if (!trigger) return text(transition?.display_label);
    const details = [];
    if (trigger.role === "provisional-trigger") {
      details.push(both(
        "暫定入力: 出来事か継続条件かをコードだけでは確定できません",
        "Provisional input: the code does not prove whether this is an occurrence or a persistent condition",
      ));
    } else if (trigger.role === "inferred-trigger") {
      details.push(both("入力から導出された判別値", "Discriminator derived from input data"));
    } else {
      details.push(both("型で確定した入力イベント", "Input event confirmed by type"));
    }
    if (trigger.roots.length) details.push(`origin: ${trigger.roots.join(", ")}`);
    if (trigger.path.length) details.push(`path: ${trigger.path.join(" → ")}`);
    return details.join("\n");
  }

  function compactMarkup(id, summary) {
    const hidden = document.createElement("span");
    hidden.className = "glyph-visually-hidden";
    hidden.textContent = summary;
    return [document.createTextNode(id), hidden];
  }

  function setCompactContent(label, id, summary) {
    const currentId = label.firstChild?.nodeType === Node.TEXT_NODE
      ? label.firstChild.textContent
      : "";
    const hidden = label.querySelector(":scope > .glyph-visually-hidden");
    if (currentId === id && hidden?.textContent === summary) return false;
    label.replaceChildren(...compactMarkup(id, summary));
    return true;
  }

  function signatureOf(machine) {
    return [
      machine?.name || "",
      machine?.transition_ir?.version || "",
      ...(machine?.transitions || []).map(transition => [
        transition.id ?? "",
        JSON.stringify(transition.trigger ?? null),
        JSON.stringify(transition.guards ?? []),
        JSON.stringify(transition.unclassified_conditions ?? []),
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
      if (!machine || Number(machine?.transition_ir?.version) < 2) return;
      const signature = signatureOf(machine);
      let changed = stage.dataset.stateTransitionIRV3Labels !== signature;

      (machine.transitions || []).forEach((transition, index) => {
        const id = transition.id || `T${index + 1}`;
        const summary = summaryOf(transition);
        const trigger = triggerOf(transition);
        const provisional = trigger?.role === "provisional-trigger";
        const unknown = (transition?.unclassified_conditions || []).length > 0;
        const compact = stage.querySelector(`.transition-label[data-transition-id="${id}"]`);
        if (compact) {
          compact.dataset.inputActionLabel = summary;
          compact.dataset.fullLabel = summary;
          if (compact.classList.contains("compact")) {
            changed = setCompactContent(compact, id, summary) || changed;
          } else if (compact.textContent !== summary) {
            compact.textContent = summary;
            changed = true;
          }
          compact.classList.toggle("provisional-trigger", provisional);
          compact.classList.toggle("unclassified-condition", unknown);
          compact.title = `${summary}\n${evidenceOf(transition)}`.trim();
          compact.dataset.triggerRole = trigger?.role || "none";
          compact.dataset.triggerConfidence = trigger?.confidence || "unknown";
        }
        const detailId = document.querySelector(
          `.transition-detail[data-transition-id="${id}"] .transition-detail-id`,
        );
        if (detailId && detailId.textContent !== summary) {
          detailId.textContent = summary;
          detailId.dataset.inputActionLabel = summary;
          changed = true;
        }
        if (detailId) {
          detailId.classList.add("input-action-label");
          detailId.classList.toggle("provisional-trigger", provisional);
          detailId.classList.toggle("unclassified-condition", unknown);
          detailId.title = evidenceOf(transition);
        }
      });

      stage.dataset.stateTransitionIRV3Labels = signature;
      stage.dataset.stateTransitionIRV3LabelsReady = "true";
      stage.dataset.stateTransitionIRV2LabelsReady = "true";
      stage.dataset.failureResultNotationReady = "true";
      if (changed) {
        document.dispatchEvent(new CustomEvent("glyph-state-transition-ir-v3-labels-ready", {
          detail: {machine: machine.name, marker: MARKER},
        }));
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
      console.error("StateTransitionIR v3 rendering failed", error);
    }), 0);
  }

  document.addEventListener("glyph-transition-input-action-labels-ready", schedule);
  document.addEventListener("glyph-uml-transition-ready", schedule);
  document.addEventListener("glyph-locale-changed", schedule);
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
    """Render v3 trigger/guard/effect roles without reclassifying compiler semantics."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
