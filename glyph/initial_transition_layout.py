from __future__ import annotations


_MARKER = "glyph-initial-transition-routing-v2"


_STYLE = r"""
<style id="glyph-initial-transition-routing-v2-style">
.initial-transition-path{
  fill:none;
  stroke:#edf3fb!important;
  stroke-width:2.4!important;
  stroke-linecap:round;
  stroke-linejoin:round;
  opacity:1!important;
}
.initial-dot{z-index:7}
.state-node.initial-target{
  box-shadow:0 0 0 2px rgba(237,243,251,.10),0 9px 22px rgba(0,0,0,.22);
}
</style>
"""


_SCRIPT = r"""
<script id="glyph-initial-transition-routing-v2-script">
(() => {
  const MARKER = "glyph-initial-transition-routing-v2";
  const DOT_RADIUS = 9;
  const NODE_CLEARANCE = 9;
  const LABEL_CLEARANCE = 6;
  const SOFT_PATH_CLEARANCE = 11;
  const HARD_PATH_CLEARANCE = 5;
  const FRAME_BUDGET_MS = 8;
  let requestedGeneration = 0;
  let completedGeneration = 0;
  let running = false;
  let timer = null;
  let destroyed = false;

  const point = (x, y) => ({x, y});
  const distance = (a, b) => Math.hypot(b.x - a.x, b.y - a.y);

  function geometry() {
    const value = window.glyphDiagramGeometry;
    if (!value || value.version < 1) throw Error("diagram geometry kernel is unavailable");
    return value;
  }

  function selectedMachine(state) {
    const machines = state?.views?.state?.machines || [];
    const selected = document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;
    return machines.find(machine => machine.name === selected) || machines[0] || null;
  }

  async function readMachine() {
    const live = typeof snapshot === "object" && snapshot ? snapshot : null;
    if (live) return selectedMachine(live);
    const response = await fetch("/api/state", {cache: "no-store"});
    if (!response.ok) return null;
    return selectedMachine(await response.json());
  }

  function stageRect(element) {
    return {
      left: element.offsetLeft,
      top: element.offsetTop,
      right: element.offsetLeft + element.offsetWidth,
      bottom: element.offsetTop + element.offsetHeight,
    };
  }

  function expanded(rect, margin) {
    return {
      left: rect.left - margin,
      top: rect.top - margin,
      right: rect.right + margin,
      bottom: rect.bottom + margin,
    };
  }

  const routeLength = points => points.slice(1).reduce(
    (total, item, index) => total + distance(points[index], item),
    0,
  );

  function shortenFromDot(points) {
    const result = points.map(item => point(item.x, item.y));
    const start = result[0];
    const next = result[1];
    const length = Math.max(1, distance(start, next));
    result[0] = point(
      start.x + (next.x - start.x) / length * DOT_RADIUS,
      start.y + (next.y - start.y) / length * DOT_RADIUS,
    );
    return result;
  }

  function candidateRoutes(target) {
    const tangentOffsets = [-84, -56, -28, 0, 28, 56, 84];
    const fractions = [.12, .25, .38, .5, .62, .75, .88];
    const laneDistances = [24, 40, 56];
    const sides = [
      {name: "top", outward: point(0, -1), tangent: point(1, 0)},
      {name: "right", outward: point(1, 0), tangent: point(0, 1)},
      {name: "bottom", outward: point(0, 1), tangent: point(1, 0)},
      {name: "left", outward: point(-1, 0), tangent: point(0, 1)},
    ];
    const candidates = [];
    for (const side of sides) {
      for (const fraction of fractions) {
        const port = side.name === "top" || side.name === "bottom"
          ? point(
            target.left + (target.right - target.left) * fraction,
            side.name === "top" ? target.top - 1 : target.bottom + 1,
          )
          : point(
            side.name === "left" ? target.left - 1 : target.right + 1,
            target.top + (target.bottom - target.top) * fraction,
          );
        for (const laneDistance of laneDistances) {
          for (const tangentOffset of tangentOffsets) {
            const lane = point(
              port.x + side.outward.x * laneDistance,
              port.y + side.outward.y * laneDistance,
            );
            const dotDistance = Math.max(88, laneDistance + 48);
            const dot = point(
              port.x + side.outward.x * dotDistance + side.tangent.x * tangentOffset,
              port.y + side.outward.y * dotDistance + side.tangent.y * tangentOffset,
            );
            const elbow = side.name === "top" || side.name === "bottom"
              ? point(dot.x, lane.y)
              : point(lane.x, dot.y);
            const raw = [dot, elbow, lane, port].filter((item, index, values) => (
              index === 0 || distance(item, values[index - 1]) > .5
            ));
            candidates.push({side: side.name, dot, port, points: shortenFromDot(raw)});
          }
        }
      }
    }
    return candidates;
  }

  function routePath(points) {
    return points.map((item, index) => (
      `${index ? "L" : "M"} ${item.x.toFixed(1)} ${item.y.toFixed(1)}`
    )).join(" ");
  }

  function routeInside(polyline, dot, width, height) {
    const margin = 13;
    if (dot.x - DOT_RADIUS < margin || dot.y - DOT_RADIUS < margin
      || dot.x + DOT_RADIUS > width - margin || dot.y + DOT_RADIUS > height - margin) {
      return false;
    }
    return polyline.every(item => item.x >= margin && item.y >= margin
      && item.x <= width - margin && item.y <= height - margin);
  }

  function fastScore(candidate, context) {
    const geom = geometry();
    const {width, height, nodeObstacles, labelObstacles, normalPolylines} = context;
    if (!routeInside(candidate.points, candidate.dot, width, height)) return null;
    if (nodeObstacles.some(rect => geom.polylineHitsRect(candidate.points, rect))) return null;
    if (labelObstacles.some(rect => geom.polylineHitsRect(candidate.points, rect))) return null;
    const crossings = geom.crossingCount(candidate.points, normalPolylines);
    const clearance = geom.minimumPolylineDistance(candidate.points, normalPolylines);
    let score = routeLength(candidate.points) + Math.max(0, candidate.points.length - 2) * 24;
    score += crossings * 100000;
    if (clearance < SOFT_PATH_CLEARANCE) score += (SOFT_PATH_CLEARANCE - clearance) * 5000;
    return {candidate, score, crossings, clearance};
  }

  function certifyCandidate(item, context) {
    const geom = geometry();
    const data = routePath(item.candidate.points);
    const polyline = geom.flattenPathData(data, {tolerance: .35, maxSegmentLength: 3});
    if (!routeInside(polyline, item.candidate.dot, context.width, context.height)) return null;
    if (context.nodeObstacles.some(rect => geom.polylineHitsRect(polyline, rect))) return null;
    if (context.labelObstacles.some(rect => geom.polylineHitsRect(polyline, rect))) return null;
    const certificate = geom.verifyPolyline(polyline, context.normalPolylines, {
      minimumClearance: HARD_PATH_CLEARANCE,
    });
    return certificate.valid ? {item, data, polyline, certificate} : null;
  }

  function geometrySignature(machine, stage, target, normalPaths, nodeObstacles, labelObstacles) {
    const rectKey = rect => [rect.left, rect.top, rect.right, rect.bottom]
      .map(value => Number(value).toFixed(1)).join(":");
    return [
      MARKER,
      machine.name,
      machine.initial_state,
      stage.clientWidth,
      stage.clientHeight,
      rectKey(stageRect(target)),
      normalPaths.map(path => path.getAttribute("d") || "").join("\u001d"),
      nodeObstacles.map(rectKey).join("\u001d"),
      labelObstacles.map(rectKey).join("\u001d"),
    ].join("\u001f");
  }

  function markFailure(stage, message, details = {}) {
    stage.dataset.initialRouteReady = "failed";
    stage.dataset.initialRouteCertificate = "failed";
    stage.dataset.initialRouteError = message;
    stage.dataset.initialRouteFailureDetails = JSON.stringify(details);
    stage.dataset.transitionPublicationReady = "false";
  }

  async function applyRouting(token) {
    const started = performance.now();
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    if (!stage || stage.dataset.transitionInputActionLabelsReady !== "true") return;
    const machine = await readMachine();
    if (!machine || token !== requestedGeneration || destroyed) return;
    const geom = geometry();
    const svg = stage.querySelector(":scope > svg.edge-svg");
    const initialPath = svg?.querySelector(":scope > path:not(.state-transition-path)");
    const dot = stage.querySelector(".initial-dot");
    const target = [...stage.querySelectorAll(".state-node")].find(node => (
      node.querySelector(".state-name")?.textContent?.trim() === String(machine.initial_state)
    ));
    if (!svg || !initialPath || !dot || !target) return;

    stage.querySelectorAll(".state-node.initial-target").forEach(node => node.classList.remove("initial-target"));
    target.classList.add("initial-target");
    const normalPaths = [...svg.querySelectorAll(":scope > path.state-transition-path")];
    const normalPolylines = normalPaths.map(path => geom.flattenPathElement(path, {
      tolerance: .35,
      maxSegmentLength: 3,
    }));
    const nodeObstacles = [...stage.querySelectorAll(".state-node")]
      .filter(node => node !== target)
      .map(node => expanded(stageRect(node), NODE_CLEARANCE));
    const labelObstacles = [
      ...stage.querySelectorAll(".edge-label.transition-label"),
      ...stage.querySelectorAll(".transition-io-cluster"),
    ].map(label => expanded(stageRect(label), LABEL_CLEARANCE));
    const signature = geometrySignature(machine, stage, target, normalPaths, nodeObstacles, labelObstacles);
    if (stage.dataset.initialTransitionRouting === signature
      && stage.dataset.initialRouteCertificate === "valid") {
      stage.dataset.initialRouteReady = "true";
      stage.dataset.initialRouteCacheHit = "true";
      stage.dataset.initialRouteDurationMs = (performance.now() - started).toFixed(2);
      completedGeneration = token;
      return;
    }

    stage.dataset.initialRouteCacheHit = "false";
    const context = {
      width: stage.clientWidth,
      height: stage.clientHeight,
      nodeObstacles,
      labelObstacles,
      normalPolylines,
    };
    const ranked = candidateRoutes(stageRect(target))
      .map(candidate => fastScore(candidate, context))
      .filter(Boolean)
      .sort((left, right) => left.score - right.score
        || left.candidate.side.localeCompare(right.candidate.side));
    stage.dataset.initialRouteCandidateCount = String(ranked.length);
    if (!ranked.length) {
      markFailure(stage, "no initial-route candidate avoids nodes and labels");
      throw Error(stage.dataset.initialRouteError);
    }

    let audited = 0;
    const result = await geom.findBudgeted(ranked, item => {
      audited += 1;
      return certifyCandidate(item, context);
    }, {
      budgetMs: FRAME_BUDGET_MS,
      cancelled: () => token !== requestedGeneration || destroyed,
    });
    if (token !== requestedGeneration || destroyed) return;
    if (!result.match) {
      markFailure(stage, "no quantized rendered route satisfies the geometry certificate", {
        candidates: ranked.length,
        audited,
        yields: result.yields,
        maxSliceMs: result.maxSliceMs,
      });
      throw Error(stage.dataset.initialRouteError);
    }

    const best = result.match;
    initialPath.setAttribute("d", best.data);
    initialPath.classList.add("initial-transition-path");
    const finalCertificate = geom.verifyPathElement(initialPath, normalPaths, {
      tolerance: .35,
      maxSegmentLength: 3,
      minimumClearance: HARD_PATH_CLEARANCE,
    });
    if (!finalCertificate.valid) {
      markFailure(stage, "final SVG geometry failed post-commit certification", finalCertificate);
      throw Error(stage.dataset.initialRouteError);
    }

    delete stage.dataset.initialRouteError;
    delete stage.dataset.initialRouteFailureDetails;
    initialPath.dataset.routeSide = best.item.candidate.side;
    initialPath.dataset.routeCrossings = String(finalCertificate.crossings);
    initialPath.dataset.routeClearance = finalCertificate.clearance.toFixed(2);
    initialPath.dataset.routeCertificate = "valid";
    dot.style.left = `${best.item.candidate.dot.x - DOT_RADIUS}px`;
    dot.style.top = `${best.item.candidate.dot.y - DOT_RADIUS}px`;
    dot.dataset.routeSide = best.item.candidate.side;

    stage.dataset.initialTransitionRouting = signature;
    stage.dataset.initialRouteReady = "true";
    stage.dataset.initialRouteCertificate = "valid";
    stage.dataset.initialRouteCrossings = String(finalCertificate.crossings);
    stage.dataset.initialRouteClearance = finalCertificate.clearance.toFixed(2);
    stage.dataset.initialRouteAuditedCandidates = String(audited);
    stage.dataset.initialRouteYieldCount = String(result.yields);
    stage.dataset.initialRouteMaxSliceMs = result.maxSliceMs.toFixed(2);
    stage.dataset.initialRouteDurationMs = (performance.now() - started).toFixed(2);
    completedGeneration = token;
    document.dispatchEvent(new CustomEvent("glyph-initial-transition-route-ready", {
      detail: {
        machine: machine.name,
        side: best.item.candidate.side,
        crossings: finalCertificate.crossings,
        clearance: finalCertificate.clearance,
        audited,
        yields: result.yields,
        maxSliceMs: result.maxSliceMs,
        marker: MARKER,
      },
    }));
  }

  async function drain() {
    if (running || destroyed) return;
    running = true;
    try {
      while (!destroyed && completedGeneration < requestedGeneration) {
        const token = requestedGeneration;
        try {
          await applyRouting(token);
          if (token === requestedGeneration) completedGeneration = token;
        } catch (error) {
          if (token !== requestedGeneration || destroyed) continue;
          const stage = document.querySelector(".state-node")?.closest(".graph-stage");
          if (stage) markFailure(stage, String(error?.message || error));
          console.error("initial transition routing failed", error);
          completedGeneration = token;
        }
      }
    } finally {
      running = false;
    }
  }

  function schedule(reason = "scheduled", delay = 0) {
    if (destroyed) return requestedGeneration;
    requestedGeneration += 1;
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    if (stage) {
      stage.dataset.initialRouteReady = "pending";
      stage.dataset.initialRouteReason = reason;
    }
    clearTimeout(timer);
    timer = setTimeout(drain, delay);
    return requestedGeneration;
  }

  for (const eventName of [
    "glyph-diagram-geometry-kernel-ready",
    "glyph-transition-input-action-labels-ready",
    "glyph-uml-transition-ready",
    "glyph-transition-layout-transaction-ready",
  ]) {
    document.addEventListener(eventName, () => schedule(eventName, 0));
  }
  document.addEventListener("change", event => {
    if (event.target?.id === "machine-select") schedule("machine-change", 0);
  });
  const view = document.getElementById("view") || document.body;
  new MutationObserver(records => {
    if (records.some(record => [...record.addedNodes, ...record.removedNodes].some(node => (
      node.nodeType === 1 && (node.matches?.(".graph-stage") || node.querySelector?.(".graph-stage"))
    )))) schedule("stage-replaced", 0);
  }).observe(view, {childList: true, subtree: true});
  for (const eventName of ["pagehide", "beforeunload"]) {
    window.addEventListener(eventName, () => {
      destroyed = true;
      clearTimeout(timer);
      requestedGeneration += 1;
    }, {once: true});
  }

  window.glyphInitialTransitionRouter = {
    marker: MARKER,
    version: 2,
    schedule,
    get generation() { return requestedGeneration; },
    get completedGeneration() { return completedGeneration; },
  };
  schedule("bootstrap", 0);
})();
</script>
"""


def enhance_initial_transition_html(html: str) -> str:
    """Install a cached, frame-budgeted and rendered-geometry-certified initial router."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
