from __future__ import annotations


_MARKER = "glyph-transition-label-layout-v1"


_TRANSITION_LABEL_STYLE = r"""
<style id="glyph-transition-label-layout-v1-style">
.edge-label.transition-label{
  z-index:4;
  max-width:260px;
  white-space:normal;
  overflow:visible;
  text-overflow:clip;
  overflow-wrap:anywhere;
  line-height:1.35;
  text-align:center;
  box-shadow:0 4px 14px rgba(0,0,0,.30);
}
.edge-label.transition-label.compact{
  min-width:30px;
  max-width:42px;
  padding:3px 7px;
  border-radius:999px;
  color:var(--text);
  border-color:rgba(88,166,255,.65);
  background:#16243a;
  font-weight:800;
  letter-spacing:.04em;
  white-space:nowrap;
}
.edge-label.transition-label.layout-fallback{
  border-color:rgba(231,191,98,.7);
  color:var(--amber);
}
.state-transition-path{
  transition:stroke .12s ease,stroke-width .12s ease,opacity .12s ease;
}
.state-transition-path.transition-focus{
  stroke:var(--blue)!important;
  stroke-width:4!important;
  opacity:1!important;
}
.transition-label.transition-focus{
  border-color:var(--blue);
  color:var(--text);
  box-shadow:0 0 0 2px rgba(88,166,255,.22),0 8px 20px rgba(0,0,0,.34);
}
.transition-index{
  margin-top:13px;
  border:1px solid var(--line);
  border-radius:11px;
  background:var(--panel);
  overflow:hidden;
}
.transition-index-title{
  display:flex;
  justify-content:space-between;
  gap:12px;
  padding:10px 12px;
  border-bottom:1px solid var(--line);
  font-weight:750;
}
.transition-index-note{
  color:var(--muted);
  font-size:11px;
  font-weight:500;
}
.transition-detail{
  display:grid;
  grid-template-columns:44px minmax(170px,auto) minmax(0,1fr) auto;
  align-items:start;
  gap:10px;
  padding:9px 12px;
  border-top:1px solid rgba(255,255,255,.045);
  cursor:pointer;
}
.transition-detail:first-of-type{border-top:0}
.transition-detail:hover,.transition-detail.transition-focus{
  background:rgba(88,166,255,.075);
}
.transition-detail-id{
  display:inline-flex;
  justify-content:center;
  align-items:center;
  min-height:24px;
  border:1px solid rgba(88,166,255,.55);
  border-radius:999px;
  color:var(--blue);
  font:800 10px ui-monospace,SFMono-Regular,Menlo,monospace;
}
.transition-detail-route{
  color:var(--text);
  font:11px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;
  overflow-wrap:anywhere;
}
.transition-detail-condition{
  color:var(--muted);
  font:11px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;
  overflow-wrap:anywhere;
  word-break:break-word;
}
.transition-detail-line{
  color:var(--faint);
  font-size:10px;
  white-space:nowrap;
}
@media(max-width:1100px){
  .transition-detail{grid-template-columns:44px 1fr auto}
  .transition-detail-condition{grid-column:2/4}
}
</style>
"""


_TRANSITION_LABEL_SCRIPT = r"""
<script id="glyph-transition-label-layout-v1-script">
(() => {
  const MARKER = "glyph-transition-label-layout-v1";
  const LONG_LABEL_LIMIT = 30;
  const DENSE_TRANSITION_LIMIT = 7;
  const GAP = 8;
  let timer = null;
  let running = false;

  const rect = (x, y, width, height) => ({x, y, width, height});
  const intersects = (a, b, gap = GAP) => !(
    a.x + a.width + gap <= b.x ||
    b.x + b.width + gap <= a.x ||
    a.y + a.height + gap <= b.y ||
    b.y + b.height + gap <= a.y
  );
  const inside = (item, width, height, margin = 10) => (
    item.x >= margin && item.y >= margin &&
    item.x + item.width <= width - margin &&
    item.y + item.height <= height - margin
  );

  function selectedMachine(state) {
    const machines = state?.views?.state?.machines || [];
    const select = document.getElementById("machine-select");
    const name = select?.selectedOptions?.[0]?.textContent;
    return machines.find(machine => machine.name === name) || machines[0] || null;
  }

  async function readMachine() {
    const response = await fetch("/api/state", {cache: "no-store"});
    if (!response.ok) throw new Error(`state request failed: ${response.status}`);
    return selectedMachine(await response.json());
  }

  function layoutSignature(machine) {
    return [
      machine.name,
      ...(machine.transitions || []).map(item => [
        item.source_state,
        item.target_state,
        item.condition,
        item.source?.line || 0,
      ].join("\u001f")),
    ].join("\u001e");
  }

  function candidates(x, y) {
    const result = [[0, 0]];
    for (const radius of [26, 48, 72, 104, 140]) {
      result.push(
        [0, -radius], [0, radius], [-radius, 0], [radius, 0],
        [-radius, -radius * .65], [radius, -radius * .65],
        [-radius, radius * .65], [radius, radius * .65],
      );
    }
    return result.map(([dx, dy]) => ({x: x + dx, y: y + dy}));
  }

  function measureAt(label, centerX, centerY) {
    label.style.left = `${centerX}px`;
    label.style.top = `${centerY}px`;
    return rect(
      centerX - label.offsetWidth / 2,
      centerY - label.offsetHeight / 2,
      label.offsetWidth,
      label.offsetHeight,
    );
  }

  function compactLabel(label, id) {
    label.textContent = id;
    label.classList.add("compact");
    label.dataset.compact = "true";
  }

  function placeLabels(stage, labels, transitions) {
    const width = stage.clientWidth;
    const baseHeight = stage.clientHeight;
    const obstacles = [...stage.querySelectorAll(".state-node")].map(node => rect(
      node.offsetLeft,
      node.offsetTop,
      node.offsetWidth,
      node.offsetHeight,
    ));
    const placed = [];
    const dense = transitions.length >= DENSE_TRANSITION_LIMIT;
    let railCursor = 18;
    let railRow = 0;
    let requiredHeight = baseHeight;

    labels.forEach((label, index) => {
      const transition = transitions[index];
      const id = `T${index + 1}`;
      const full = String(transition?.condition ?? label.title ?? label.textContent ?? "");
      label.dataset.transitionId = id;
      label.dataset.fullLabel = full;
      label.title = full;
      label.classList.add("transition-label");
      label.classList.remove("compact", "layout-fallback");
      label.dataset.compact = "false";

      const preferredX = Number.parseFloat(label.style.left) || width / 2;
      const preferredY = Number.parseFloat(label.style.top) || baseHeight / 2;
      label.textContent = full;
      if (dense || full.length > LONG_LABEL_LIMIT) compactLabel(label, id);

      const tryPlace = () => {
        for (const point of candidates(preferredX, preferredY)) {
          const candidate = measureAt(label, point.x, point.y);
          if (!inside(candidate, width, baseHeight)) continue;
          if (obstacles.some(item => intersects(candidate, item))) continue;
          if (placed.some(item => intersects(candidate, item))) continue;
          placed.push(candidate);
          return true;
        }
        return false;
      };

      if (tryPlace()) return;
      if (label.dataset.compact !== "true") {
        compactLabel(label, id);
        if (tryPlace()) return;
      }

      const itemWidth = Math.max(42, label.offsetWidth);
      if (railCursor + itemWidth > width - 18) {
        railCursor = 18;
        railRow += 1;
      }
      const centerX = railCursor + itemWidth / 2;
      const centerY = baseHeight + 28 + railRow * 38;
      const fallback = measureAt(label, centerX, centerY);
      label.classList.add("layout-fallback");
      placed.push(fallback);
      railCursor += itemWidth + 12;
      requiredHeight = Math.max(requiredHeight, fallback.y + fallback.height + 16);
    });

    if (requiredHeight > baseHeight) {
      stage.style.height = `${Math.ceil(requiredHeight)}px`;
      const svg = stage.querySelector(":scope > svg.edge-svg");
      if (svg) svg.setAttribute("height", String(Math.ceil(requiredHeight)));
    }
  }

  function transitionIndex(machine) {
    const rows = (machine.transitions || []).map((transition, index) => {
      const id = `T${index + 1}`;
      const line = transition.source?.line || 0;
      return `<div class="transition-detail" data-transition-id="${id}" data-line="${line}">` +
        `<span class="transition-detail-id">${id}</span>` +
        `<span class="transition-detail-route">${escapeHtml(transition.source_state)} → ${escapeHtml(transition.target_state)}</span>` +
        `<span class="transition-detail-condition">${escapeHtml(transition.condition || "otherwise")}</span>` +
        `<span class="transition-detail-line">L${line || "?"}</span>` +
      `</div>`;
    }).join("");
    return `<section class="transition-index" data-layout-owner="${MARKER}">` +
      `<div class="transition-index-title"><span>Transition details</span>` +
      `<span class="transition-index-note">長いラベルは図中のIDと対応する</span></div>` +
      rows +
    `</section>`;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
    })[character]);
  }

  function bindTransitionFocus(stage) {
    const elements = document.querySelectorAll("[data-transition-id]");
    const setFocused = (id, active) => {
      document.querySelectorAll(`[data-transition-id="${id}"]`).forEach(element => {
        element.classList.toggle("transition-focus", active);
      });
    };
    elements.forEach(element => {
      const id = element.dataset.transitionId;
      element.addEventListener("mouseenter", () => setFocused(id, true));
      element.addEventListener("mouseleave", () => setFocused(id, false));
    });
    stage.querySelectorAll(".transition-detail").forEach(row => {
      row.addEventListener("click", () => {
        const line = Number(row.dataset.line || 0);
        if (line && typeof jumpToLine === "function") jumpToLine(line);
      });
    });
  }

  async function enhance() {
    if (running) return;
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    if (!stage) return;
    running = true;
    try {
      const machine = await readMachine();
      if (!machine) return;
      const signature = layoutSignature(machine);
      if (stage.dataset.transitionLayout === signature) return;
      stage.dataset.transitionLayout = signature;

      document.querySelectorAll(`[data-layout-owner="${MARKER}"]`).forEach(item => item.remove());
      const transitions = machine.transitions || [];
      const labels = [...stage.querySelectorAll(".edge-label")].slice(0, transitions.length);
      const paths = [...stage.querySelectorAll(":scope > svg.edge-svg > path")].slice(0, transitions.length);
      labels.forEach((label, index) => label.dataset.transitionId = `T${index + 1}`);
      paths.forEach((path, index) => {
        path.dataset.transitionId = `T${index + 1}`;
        path.classList.add("state-transition-path");
      });

      placeLabels(stage, labels, transitions);
      const shell = stage.closest(".canvas-shell");
      if (shell) shell.insertAdjacentHTML("afterend", transitionIndex(machine));
      bindTransitionFocus(stage);
      stage.dataset.labelLayoutReady = "true";
      document.dispatchEvent(new CustomEvent("glyph-transition-layout-ready", {
        detail: {machine: machine.name, transitions: transitions.length},
      }));
    } finally {
      running = false;
    }
  }

  function schedule(force = false) {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (force) {
        const stage = document.querySelector(".state-node")?.closest(".graph-stage");
        if (stage) delete stage.dataset.transitionLayout;
      }
      enhance().catch(error => console.error("transition label layout failed", error));
    }, 35);
  }

  const observer = new MutationObserver(() => schedule(false));
  const target = document.getElementById("view");
  if (target) observer.observe(target, {childList: true, subtree: true});
  window.addEventListener("resize", () => schedule(true));
  document.addEventListener("change", event => {
    if (event.target?.id === "machine-select") schedule(true);
  });
  schedule(true);
})();
</script>
"""


def enhance_diagram_html(html: str) -> str:
    """Add deterministic transition-label packing and a full transition index.

    The base renderer remains backend-neutral. This transformation only adds a
    presentation layer: short labels are packed near their edges, while dense or
    long labels are replaced by compact IDs whose full text is listed below the
    graph. The function is idempotent so repeated launcher imports are safe.
    """

    if _MARKER in html:
        return html
    insertion = _TRANSITION_LABEL_STYLE + _TRANSITION_LABEL_SCRIPT
    if "</body>" not in html:
        raise ValueError("diagram HTML has no closing body tag")
    return html.replace("</body>", insertion + "\n</body>", 1)
