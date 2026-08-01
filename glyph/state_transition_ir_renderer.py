from __future__ import annotations


_MARKER = "glyph-state-transition-ir-v4-renderer"

_STYLE = r"""
<style id="glyph-state-transition-ir-v4-renderer-style">
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
.transition-label[data-rtai-semantic-status],
.transition-detail-id[data-rtai-semantic-status]{
  position:relative;
}
.transition-label[data-rtai-semantic-status]::after,
.transition-detail-id[data-rtai-semantic-status]::after{
  content:attr(data-rtai-semantic-label);
  display:none;
  position:absolute;
  left:calc(100% + 5px);
  top:50%;
  transform:translateY(-50%);
  z-index:12;
  align-items:center;
  padding:1px 5px;
  border:1px solid currentColor;
  border-radius:999px;
  font-size:9px;
  font-weight:700;
  line-height:1.25;
  letter-spacing:.02em;
  vertical-align:1px;
  white-space:nowrap;
  pointer-events:none;
  box-shadow:0 1px 4px rgba(15,23,42,.12);
}
.graph-stage[data-rtai-projection-mode="strict-exact"]
  .transition-label[data-rtai-semantic-status]::after,
.graph-stage[data-rtai-projection-mode="strict-exact"]
  .transition-detail-id[data-rtai-semantic-status]::after,
.transition-label[data-rtai-semantic-status]:hover::after,
.transition-detail-id[data-rtai-semantic-status]:hover::after{
  display:inline-flex;
}
.transition-label.rtai-semantic-exact,
.transition-detail-id.rtai-semantic-exact{
  --rtai-semantic-color:#15803d;
}
.transition-label.rtai-semantic-may,
.transition-detail-id.rtai-semantic-may{
  --rtai-semantic-color:#a16207;
}
.transition-label.rtai-semantic-unknown,
.transition-detail-id.rtai-semantic-unknown{
  --rtai-semantic-color:#6b7280;
}
.transition-label.rtai-semantic-exact::after,
.transition-label.rtai-semantic-may::after,
.transition-label.rtai-semantic-unknown::after,
.transition-detail-id.rtai-semantic-exact::after,
.transition-detail-id.rtai-semantic-may::after,
.transition-detail-id.rtai-semantic-unknown::after{
  color:var(--rtai-semantic-color);
  background:color-mix(in srgb,var(--rtai-semantic-color) 8%,white);
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
<script id="glyph-state-transition-ir-v4-renderer-script">
(() => {
  const MARKER = "glyph-state-transition-ir-v4-renderer";
  const SEMANTIC_CLASSES = [
    "rtai-semantic-exact",
    "rtai-semantic-may",
    "rtai-semantic-unknown",
  ];
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

  function semanticStatusOf(transition) {
    const raw = transition?.rtai_semantic_status;
    const status = ["exact", "may", "unknown"].includes(text(raw?.status))
      ? text(raw.status)
      : "unknown";
    return {
      status,
      reason: text(raw?.reason) || "native Evidence status is unavailable",
      label: status === "exact" ? "Exact" : status === "may" ? "May" : "Unknown",
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
    const raw = window.GlyphExecutionContext?.actionFor?.(transition) ?? transition?.action;
    return typeof raw === "string"
      ? text(raw)
      : text(raw?.display) || text(raw?.expression);
  }

  function summaryOf(transition) {
    const input = inputOf(transition);
    const action = actionOf(transition);
    const failure = text(transition?.failure_type);
    let summary = action ? `${input}➡︎${action}` : input;
    if (failure) summary += ` | ${failure}`;
    return summary;
  }

  function evidenceOf(transition) {
    const trigger = triggerOf(transition);
    const semantic = semanticStatusOf(transition);
    const details = [
      semantic.status === "exact"
        ? both("意味論: Exact（確定表示条件を満たす）", "Semantics: Exact (all exact-display conditions are satisfied)")
        : semantic.status === "may"
          ? both("意味論: May（実行可能だが一意性を証明していない）", "Semantics: May (possible, but uniqueness is not proven)")
          : both("意味論: Unknown（解析上の未解決要因がある）", "Semantics: Unknown (analysis has unresolved causes)"),
      `reason: ${semantic.reason}`,
    ];
    if (!trigger) {
      const legacy = text(transition?.display_label);
      if (legacy) details.push(legacy);
      return details.join("\n");
    }
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

  function applySemanticStatus(element, semantic) {
    if (!element) return;
    SEMANTIC_CLASSES.forEach(className => element.classList.remove(className));
    element.classList.add(`rtai-semantic-${semantic.status}`);
    element.dataset.rtaiSemanticStatus = semantic.status;
    element.dataset.rtaiSemanticLabel = semantic.label;
    element.dataset.rtaiSemanticReason = semantic.reason;
  }

  function signatureOf(machine) {
    return [
      machine?.name || "",
      machine?.transition_ir?.version || "",
      machine?.analysis?.evidence_projection_mode || "shadow",
      window.GlyphExecutionContext?.signature?.() || "auto",
      ...(machine?.transitions || []).map(transition => [
        transition.id ?? "",
        JSON.stringify(transition.trigger ?? null),
        JSON.stringify(transition.guards ?? []),
        JSON.stringify(transition.unclassified_conditions ?? []),
        JSON.stringify(transition.rtai_semantic_status ?? null),
        actionOf(transition),
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
      stage.dataset.rtaiProjectionMode = text(machine?.analysis?.evidence_projection_mode) || "shadow";
      const signature = signatureOf(machine);
      let changed = stage.dataset.stateTransitionIRV4Labels !== signature;

      (machine.transitions || []).forEach((transition, index) => {
        const id = transition.id || `T${index + 1}`;
        const summary = summaryOf(transition);
        const trigger = triggerOf(transition);
        const semantic = semanticStatusOf(transition);
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
          applySemanticStatus(compact, semantic);
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
          applySemanticStatus(detailId, semantic);
          detailId.title = evidenceOf(transition);
        }
      });

      stage.dataset.stateTransitionIRV4Labels = signature;
      stage.dataset.stateTransitionIRV4LabelsReady = "true";
      stage.dataset.stateTransitionIRV3LabelsReady = "true";
      stage.dataset.stateTransitionIRV2LabelsReady = "true";
      stage.dataset.failureResultNotationReady = "true";
      if (changed) {
        document.dispatchEvent(new CustomEvent("glyph-state-transition-ir-v4-labels-ready", {
          detail: {machine: machine.name, marker: MARKER},
        }));
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
      console.error("StateTransitionIR rendering failed", error);
    }), 0);
  }

  document.addEventListener("glyph-transition-input-action-labels-ready", schedule);
  document.addEventListener("glyph-uml-transition-ready", schedule);
  document.addEventListener("glyph-locale-changed", schedule);
  document.addEventListener("glyph-execution-context-changed", schedule);
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
    """Render trigger/guard/Action roles and Evidence status without reanalysis."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
