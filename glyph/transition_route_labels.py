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
  const GAP = 8;
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

  function rectangle(element, centerX = null, centerY = null) {
    const left = centerX === null ? element.offsetLeft : centerX - element.offsetWidth / 2;
    const top = centerY === null ? element.offsetTop : centerY - element.offsetHeight / 2;
    return {left, top, right: left + element.offsetWidth, bottom: top + element.offsetHeight};
  }

  function intersects(left, right) {
    return !(
      left.right + GAP <= right.left
      || right.right + GAP <= left.left
      || left.bottom + GAP <= right.top
      || right.bottom + GAP <= left.top
    );
  }

  function inside(item, width, height) {
    return item.left >= 10 && item.top >= 10 && item.right <= width - 10 && item.bottom <= height - 10;
  }

  function candidates(x, y) {
    const result = [[0, 0]];
    for (const radius of [30, 54, 82, 116, 154, 196]) {
      result.push(
        [0, -radius], [0, radius], [-radius, 0], [radius, 0],
        [-radius, -radius * .65], [radius, -radius * .65],
        [-radius, radius * .65], [radius, radius * .65],
      );
    }
    return result.map(([dx, dy]) => ({x: x + dx, y: y + dy}));
  }

  function reflowCompactLabels(stage) {
    const labels = [...stage.querySelectorAll(".transition-label.compact.input-action-label")];
    if (!labels.length) return;

    const width = stage.clientWidth;
    const baseHeight = stage.clientHeight;
    const occupied = [
      ...[...stage.querySelectorAll(".state-node")].map(node => rectangle(node)),
      ...[...stage.querySelectorAll(".transition-label:not(.compact)")].map(label => rectangle(label)),
    ];
    let requiredHeight = baseHeight;
    let railX = 18;
    let railRow = 0;

    labels.forEach(label => {
      const preferredX = Number.parseFloat(label.style.left) || width / 2;
      const preferredY = Number.parseFloat(label.style.top) || baseHeight / 2;
      let placed = false;

      for (const point of candidates(preferredX, preferredY)) {
        label.style.left = `${point.x}px`;
        label.style.top = `${point.y}px`;
        const candidate = rectangle(label, point.x, point.y);
        if (!inside(candidate, width, baseHeight)) continue;
        if (occupied.some(item => intersects(candidate, item))) continue;
        occupied.push(candidate);
        placed = true;
        break;
      }

      if (placed) return;

      const itemWidth = label.offsetWidth;
      if (railX + itemWidth > width - 18) {
        railX = 18;
        railRow += 1;
      }
      const centerX = railX + itemWidth / 2;
      const centerY = baseHeight + 28 + railRow * Math.max(40, label.offsetHeight + 12);
      label.style.left = `${centerX}px`;
      label.style.top = `${centerY}px`;
      label.classList.add("layout-fallback");
      const fallback = rectangle(label, centerX, centerY);
      occupied.push(fallback);
      railX += itemWidth + 12;
      requiredHeight = Math.max(requiredHeight, fallback.bottom + 16);
    });

    if (requiredHeight > baseHeight) {
      stage.style.height = `${Math.ceil(requiredHeight)}px`;
      const svg = stage.querySelector(":scope > svg.edge-svg");
      if (svg) svg.setAttribute("height", String(Math.ceil(requiredHeight)));
    }
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

      const note = document.querySelector(".transition-index-note");
      if (note) note.textContent = "図中は入力→アクションの要約。完全な遷移情報は各行に表示する";
      reflowCompactLabels(stage);

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
