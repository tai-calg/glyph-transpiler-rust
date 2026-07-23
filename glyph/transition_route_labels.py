from __future__ import annotations


_MARKER = "glyph-transition-route-labels-v1"


_STYLE = r"""
<style id="glyph-transition-route-labels-v1-style">
.edge-label.transition-label.compact.route-label{
  min-width:0;
  max-width:180px;
  border-radius:7px;
  padding:3px 7px;
  white-space:normal;
  overflow-wrap:anywhere;
  letter-spacing:0;
  font-weight:750;
}
.transition-detail-id.route-label{
  width:max-content;
  max-width:190px;
  padding:3px 7px;
  border-radius:7px;
  overflow-wrap:anywhere;
  text-align:center;
}
</style>
"""


_SCRIPT = r"""
<script id="glyph-transition-route-labels-v1-script">
(() => {
  const MARKER = "glyph-transition-route-labels-v1";
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

  function routeOf(transition) {
    return `${transition?.source_state ?? "?"}→${transition?.target_state ?? "?"}`;
  }

  function signatureOf(machine) {
    return [
      machine?.name || "",
      ...(machine?.transitions || []).map(transition => [
        transition.source_state,
        transition.target_state,
        transition.display_label ?? transition.condition ?? "",
      ].join("\u001f")),
    ].join("\u001e");
  }

  async function applyRouteLabels() {
    if (running) return;
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    if (!stage || stage.dataset.labelLayoutReady !== "true") return;
    running = true;
    try {
      const machine = await readMachine();
      if (!machine) return;
      const signature = signatureOf(machine);
      if (stage.dataset.transitionRouteLabels === signature) return;
      stage.dataset.transitionRouteLabels = signature;

      (machine.transitions || []).forEach((transition, index) => {
        const internalId = `T${index + 1}`;
        const route = routeOf(transition);
        const label = stage.querySelector(`.transition-label[data-transition-id="${internalId}"]`);
        if (label?.classList.contains("compact")) {
          label.textContent = route;
          label.classList.add("route-label");
          label.dataset.routeLabel = route;
        }
        const detailId = document.querySelector(
          `.transition-detail[data-transition-id="${internalId}"] .transition-detail-id`,
        );
        if (detailId) {
          detailId.textContent = route;
          detailId.classList.add("route-label");
          detailId.dataset.routeLabel = route;
        }
      });

      stage.dataset.transitionRouteLabelsReady = "true";
      document.dispatchEvent(new CustomEvent("glyph-transition-route-labels-ready", {
        detail: {machine: machine.name, marker: MARKER},
      }));
    } finally {
      running = false;
    }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(() => applyRouteLabels().catch(() => {}), 0);
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
    """Replace visible compact T identifiers with source→target routes.

    T identifiers remain internal correlation keys for hover/focus behavior. Short
    event/guard/action labels remain unchanged; only labels that were compacted by
    the collision-avoidance layer are replaced visually.
    """

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
