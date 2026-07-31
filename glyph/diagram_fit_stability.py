from __future__ import annotations


_MARKER = "glyph-diagram-fit-stability-v1"


_STYLE = r"""
<style id="glyph-diagram-fit-stability-v1-style">
.graph-stage[data-fit-visibility-state="failed"]{
  visibility:hidden!important;
}
</style>
"""


_SCRIPT = r"""
<script id="glyph-diagram-fit-stability-v1-script">
(() => {
  const MARKER = "glyph-diagram-fit-stability-v1";
  const MIN_SCALE = .25;
  const MAX_SCALE = 3;
  const FIT_MARGIN = 32;
  const VISIBILITY_TOLERANCE = 2;
  const SETTLE_DELAY_MS = 80;
  let generation = 0;
  let timer = null;
  let shellObserver = null;
  let diagnosticsObserver = null;
  let observedShell = null;
  let observedDiagnostics = null;
  let destroyed = false;

  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));
  const roundScale = value => Math.round(clamp(value, MIN_SCALE, MAX_SCALE) * 100) / 100;
  const nextPaint = () => new Promise(resolve => (
    requestAnimationFrame(() => requestAnimationFrame(resolve))
  ));

  function activeStage() {
    const active = document.querySelector(".tab.active")?.dataset.tab;
    const view = active === "state"
      ? document.querySelector(".state-node")
      : document.querySelector(".graph-node,.state-node");
    return view?.closest(".graph-stage") || document.querySelector(".graph-stage");
  }

  function diagramIdentity(stage) {
    const tab = document.querySelector(".tab.active")?.dataset.tab || "state";
    const index = tab === "state"
      ? document.getElementById("machine-select")?.value || 0
      : document.getElementById("system-select")?.value || 0;
    return `${stage.dataset.diagramDigest || "source"}:${tab}:${index}`;
  }

  function stageSize(stage) {
    const styledWidth = Number.parseFloat(stage.style.width || "0") || 0;
    const styledHeight = Number.parseFloat(stage.style.height || "0") || 0;
    return {
      width: Math.max(1, styledWidth, stage.scrollWidth),
      height: Math.max(1, styledHeight, stage.scrollHeight),
    };
  }

  function surfaceFor(shell, stage) {
    if (stage.parentElement?.classList.contains("glyph-zoom-surface")) {
      return stage.parentElement;
    }
    const surface = document.createElement("div");
    surface.className = "glyph-zoom-surface";
    shell.insertBefore(surface, stage);
    surface.appendChild(stage);
    return surface;
  }

  function updateControls(scale) {
    const value = document.getElementById("diagram-zoom-value");
    if (value) value.textContent = `${Math.round(scale * 100)}%`;
    const out = document.getElementById("diagram-zoom-out");
    const inside = document.getElementById("diagram-zoom-in");
    if (out) out.disabled = scale <= MIN_SCALE + .001;
    if (inside) inside.disabled = scale >= MAX_SCALE - .001;
  }

  function fitMode() {
    const viewport = window.glyphDiagramViewport;
    if (!viewport || viewport.version < 2 || typeof viewport.mode !== "function") {
      return "";
    }
    return viewport.mode();
  }

  function publicationReady(stage) {
    return stage.dataset.transitionLayoutState === "ready"
      && stage.dataset.transitionPublicationReady === "true"
      && stage.dataset.layoutCertificateState === "valid";
  }

  function visibleElements(stage) {
    return [
      ...stage.querySelectorAll(".state-node"),
      ...stage.querySelectorAll(".transition-io-cluster"),
      ...stage.querySelectorAll(".graph-node"),
    ].filter((element, index, values) => values.indexOf(element) === index);
  }

  function visibilityAudit(shell, stage) {
    const shellRect = shell.getBoundingClientRect();
    const bounds = {
      left: shellRect.left,
      top: shellRect.top,
      right: shellRect.left + shell.clientWidth,
      bottom: shellRect.top + shell.clientHeight,
    };
    const outside = [];
    for (const [index, element] of visibleElements(stage).entries()) {
      const rect = element.getBoundingClientRect();
      const id = element.dataset.transitionId
        || element.querySelector(".state-name,.node-name")?.textContent?.trim()
        || `element-${index}`;
      if (rect.left < bounds.left - VISIBILITY_TOLERANCE
        || rect.top < bounds.top - VISIBILITY_TOLERANCE
        || rect.right > bounds.right + VISIBILITY_TOLERANCE
        || rect.bottom > bounds.bottom + VISIBILITY_TOLERANCE) {
        outside.push({
          id,
          rect: {
            left: rect.left,
            top: rect.top,
            right: rect.right,
            bottom: rect.bottom,
          },
        });
      }
    }
    return {
      ok: outside.length === 0,
      outside,
      shell: bounds,
      count: visibleElements(stage).length,
      scale: Number.parseFloat(stage.dataset.viewportScale || "1") || 1,
    };
  }

  async function silentFit(shell, stage, token) {
    const size = stageSize(stage);
    const availableWidth = Math.max(80, shell.clientWidth - FIT_MARGIN * 2);
    const availableHeight = Math.max(80, shell.clientHeight - FIT_MARGIN * 2);
    const scale = roundScale(Math.min(
      availableWidth / size.width,
      availableHeight / size.height,
    ));
    const surface = surfaceFor(shell, stage);
    stage.style.transform = `scale(${scale})`;
    stage.dataset.viewportScale = String(scale);
    surface.style.width = `${Math.ceil(size.width * scale)}px`;
    surface.style.height = `${Math.ceil(size.height * scale)}px`;
    surface.dataset.viewportScale = String(scale);

    const identity = diagramIdentity(stage);
    sessionStorage.setItem(`glyph.diagram.viewport-scale.v1:${identity}`, String(scale));
    sessionStorage.setItem(`glyph.diagram.viewport-mode.v1:${identity}`, "fit");
    updateControls(scale);

    await nextPaint();
    if (token !== generation || destroyed) return null;
    shell.scrollLeft = Math.max(
      0,
      surface.offsetLeft + size.width * scale / 2 - shell.clientWidth / 2,
    );
    shell.scrollTop = Math.max(
      0,
      surface.offsetTop + size.height * scale / 2 - shell.clientHeight / 2,
    );
    shell.dispatchEvent(new Event("scroll"));
    await nextPaint();
    if (token !== generation || destroyed) return null;
    return visibilityAudit(shell, stage);
  }

  async function stabilize(reason, token) {
    const stage = activeStage();
    const shell = stage?.closest(".canvas-shell");
    if (!stage || !shell || token !== generation || destroyed) return;
    if (!publicationReady(stage)) {
      stage.dataset.fitVisibilityState = "deferred";
      stage.dataset.fitVisibilityReason = reason;
      return;
    }
    const mode = fitMode();
    if (mode && mode !== "fit") {
      stage.dataset.fitVisibilityState = `preserved:${mode}`;
      stage.dataset.fitVisibilityReason = reason;
      return;
    }

    stage.dataset.fitVisibilityState = "pending";
    stage.dataset.fitVisibilityReason = reason;
    let audit = await silentFit(shell, stage, token);
    if (!audit || token !== generation || destroyed) return;
    if (!audit.ok) {
      await nextPaint();
      if (token !== generation || destroyed) return;
      audit = await silentFit(shell, stage, token);
      if (!audit || token !== generation || destroyed) return;
    }
    stage.dataset.fitVisibilityScale = String(audit.scale);
    stage.dataset.fitVisibilityCount = String(audit.count);
    stage.dataset.fitVisibilityDetails = JSON.stringify(audit.outside);
    if (!audit.ok) {
      stage.dataset.fitVisibilityState = "failed";
      console.error("diagram fit visibility certification failed", {
        marker: MARKER,
        reason,
        audit,
      });
      document.dispatchEvent(new CustomEvent("glyph-diagram-fit-visibility-failed", {
        detail: {marker: MARKER, reason, audit},
      }));
      return;
    }
    stage.dataset.fitVisibilityState = "ready";
    delete stage.dataset.fitVisibilityDetails;
    document.dispatchEvent(new CustomEvent("glyph-diagram-fit-visibility-ready", {
      detail: {marker: MARKER, reason, scale: audit.scale, count: audit.count},
    }));
  }

  function schedule(reason = "scheduled", delay = SETTLE_DELAY_MS) {
    if (destroyed) return generation;
    generation += 1;
    const token = generation;
    clearTimeout(timer);
    timer = setTimeout(() => stabilize(reason, token), delay);
    return token;
  }

  function bindObservers() {
    const stage = activeStage();
    const shell = stage?.closest(".canvas-shell") || null;
    const diagnostics = document.getElementById("diagnostics");
    if (shell !== observedShell) {
      shellObserver?.disconnect();
      observedShell = shell;
      shellObserver = null;
      if (shell && typeof ResizeObserver === "function") {
        shellObserver = new ResizeObserver(() => schedule("canvas-shell-resize", 40));
        shellObserver.observe(shell);
      }
    }
    if (diagnostics !== observedDiagnostics) {
      diagnosticsObserver?.disconnect();
      observedDiagnostics = diagnostics;
      diagnosticsObserver = null;
      if (diagnostics && typeof ResizeObserver === "function") {
        diagnosticsObserver = new ResizeObserver(() => schedule("diagnostics-resize", 40));
        diagnosticsObserver.observe(diagnostics);
      }
    }
  }

  for (const eventName of [
    "glyph-layout-publication-certificate-ready",
    "glyph-transition-layout-transaction-ready",
    "glyph-layout-shelf-viewport-ready",
    "glyph-layout-compact-shelf-repair-ready",
    "glyph-layout-shelf-repair-ready",
    "glyph-locale-changed",
  ]) {
    document.addEventListener(eventName, () => {
      bindObservers();
      schedule(eventName, 40);
    });
  }
  document.addEventListener("change", event => {
    if (event.target?.matches?.("#machine-select,#system-select")) {
      bindObservers();
      schedule("selection-change", 80);
    }
  });
  new MutationObserver(() => {
    bindObservers();
    schedule("view-mutation", 100);
  }).observe(document.getElementById("view") || document.body, {
    childList: true,
    subtree: true,
  });
  window.addEventListener("resize", () => schedule("window-resize", 80));
  for (const eventName of ["pagehide", "beforeunload"]) {
    window.addEventListener(eventName, () => {
      destroyed = true;
      clearTimeout(timer);
      shellObserver?.disconnect();
      diagnosticsObserver?.disconnect();
    }, {once: true});
  }

  window.glyphDiagramFitStability = {
    marker: MARKER,
    version: 1,
    schedule,
    audit: () => {
      const stage = activeStage();
      const shell = stage?.closest(".canvas-shell");
      return stage && shell
        ? visibilityAudit(shell, stage)
        : {ok: false, outside: [{id: "stage", reason: "missing"}], count: 0};
    },
    get generation() { return generation; },
  };
  bindObservers();
  schedule("bootstrap", 120);
})();
</script>
"""


def enhance_diagram_fit_stability_html(html: str) -> str:
    """Keep fit-mode publication geometry fully visible after shell resizing."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
