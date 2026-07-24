from __future__ import annotations


_MARKER = "glyph-initial-transition-routing-v1"


_STYLE = r"""
<style id="glyph-initial-transition-routing-v1-style">
.initial-transition-path{
  fill:none;
  stroke:#edf3fb!important;
  stroke-width:2.4!important;
  stroke-linecap:round;
  stroke-linejoin:round;
  opacity:1!important;
}
.initial-dot{
  z-index:7;
}
.state-node.initial-target{
  box-shadow:0 0 0 2px rgba(237,243,251,.10),0 9px 22px rgba(0,0,0,.22);
}
</style>
"""


_SCRIPT = r"""
<script id="glyph-initial-transition-routing-v1-script">
(() => {
  const MARKER = "glyph-initial-transition-routing-v1";
  const DOT_RADIUS = 9;
  const NODE_CLEARANCE = 9;
  const LABEL_CLEARANCE = 6;
  const PATH_CLEARANCE = 11;
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

  const point = (x, y) => ({x, y});
  const distance = (a, b) => Math.hypot(b.x - a.x, b.y - a.y);
  const routeLength = points => points.slice(1).reduce(
    (total, item, index) => total + distance(points[index], item),
    0,
  );

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

  function orientation(a, b, c) {
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  }

  function between(value, first, second, tolerance = .001) {
    return value >= Math.min(first, second) - tolerance
      && value <= Math.max(first, second) + tolerance;
  }

  function segmentsIntersect(a, b, c, d) {
    const abC = orientation(a, b, c);
    const abD = orientation(a, b, d);
    const cdA = orientation(c, d, a);
    const cdB = orientation(c, d, b);
    if (((abC > 0 && abD < 0) || (abC < 0 && abD > 0))
      && ((cdA > 0 && cdB < 0) || (cdA < 0 && cdB > 0))) return true;
    const collinear = (value, p, q, r) => Math.abs(value) < .001
      && between(r.x, p.x, q.x) && between(r.y, p.y, q.y);
    return collinear(abC, a, b, c)
      || collinear(abD, a, b, d)
      || collinear(cdA, c, d, a)
      || collinear(cdB, c, d, b);
  }

  function segmentHitsRect(a, b, rect) {
    if (a.x >= rect.left && a.x <= rect.right && a.y >= rect.top && a.y <= rect.bottom) return true;
    if (b.x >= rect.left && b.x <= rect.right && b.y >= rect.top && b.y <= rect.bottom) return true;
    const topLeft = point(rect.left, rect.top);
    const topRight = point(rect.right, rect.top);
    const bottomRight = point(rect.right, rect.bottom);
    const bottomLeft = point(rect.left, rect.bottom);
    return segmentsIntersect(a, b, topLeft, topRight)
      || segmentsIntersect(a, b, topRight, bottomRight)
      || segmentsIntersect(a, b, bottomRight, bottomLeft)
      || segmentsIntersect(a, b, bottomLeft, topLeft);
  }

  function routeHitsRect(points, rect) {
    return points.slice(1).some((item, index) => segmentHitsRect(points[index], item, rect));
  }

  function sampleSvgPath(path, step = 4) {
    const length = path.getTotalLength();
    const samples = [];
    for (let offset = 0; offset < length; offset += step) {
      const value = path.getPointAtLength(offset);
      samples.push(point(value.x, value.y));
    }
    const last = path.getPointAtLength(length);
    samples.push(point(last.x, last.y));
    return samples;
  }

  function sampleRoute(points, step = 4) {
    const result = [];
    points.slice(1).forEach((end, index) => {
      const start = points[index];
      const length = distance(start, end);
      const count = Math.max(1, Math.ceil(length / step));
      for (let item = 0; item < count; item += 1) {
        const ratio = item / count;
        result.push(point(
          start.x + (end.x - start.x) * ratio,
          start.y + (end.y - start.y) * ratio,
        ));
      }
    });
    result.push(points.at(-1));
    return result;
  }

  function minimumDistance(left, right) {
    let minimum = Number.POSITIVE_INFINITY;
    for (const a of left) {
      for (const b of right) {
        minimum = Math.min(minimum, distance(a, b));
      }
    }
    return minimum;
  }

  function crossingCount(points, normalPolylines) {
    let crossings = 0;
    const segments = points.slice(1).map((end, index) => [points[index], end]);
    for (const polyline of normalPolylines) {
      const normalSegments = polyline.slice(1).map((end, index) => [polyline[index], end]);
      for (const [a, b] of segments) {
        for (const [c, d] of normalSegments) {
          if (segmentsIntersect(a, b, c, d)) crossings += 1;
        }
      }
    }
    return crossings;
  }

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
    const tangentOffsets = [-48, 0, 48];
    const fractions = [.28, .72];
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
          ? point(target.left + (target.right - target.left) * fraction,
            side.name === "top" ? target.top - 1 : target.bottom + 1)
          : point(side.name === "left" ? target.left - 1 : target.right + 1,
            target.top + (target.bottom - target.top) * fraction);
        for (const tangentOffset of tangentOffsets) {
          const lane = point(
            port.x + side.outward.x * 28,
            port.y + side.outward.y * 28,
          );
          const dot = point(
            port.x + side.outward.x * 76 + side.tangent.x * tangentOffset,
            port.y + side.outward.y * 76 + side.tangent.y * tangentOffset,
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
    return candidates;
  }

  function routeInside(points, dot, width, height) {
    const margin = 13;
    if (dot.x - DOT_RADIUS < margin || dot.y - DOT_RADIUS < margin
      || dot.x + DOT_RADIUS > width - margin || dot.y + DOT_RADIUS > height - margin) return false;
    return points.every(item => item.x >= margin && item.y >= margin
      && item.x <= width - margin && item.y <= height - margin);
  }

  function scoreCandidate(candidate, context) {
    const {width, height, nodeObstacles, labelObstacles, normalPolylines} = context;
    if (!routeInside(candidate.points, candidate.dot, width, height)) return null;
    if (nodeObstacles.some(rect => routeHitsRect(candidate.points, rect))) return null;
    if (labelObstacles.some(rect => routeHitsRect(candidate.points, rect))) return null;

    const routeSamples = sampleRoute(candidate.points);
    const crossings = crossingCount(candidate.points, normalPolylines);
    let minimum = Number.POSITIVE_INFINITY;
    for (const normal of normalPolylines) minimum = Math.min(minimum, minimumDistance(routeSamples, normal));
    if (!normalPolylines.length) minimum = 999;

    let score = routeLength(candidate.points) + Math.max(0, candidate.points.length - 2) * 24;
    score += crossings * 100000;
    if (minimum < PATH_CLEARANCE) score += (PATH_CLEARANCE - minimum) * 5000;
    return {candidate, score, crossings, minimum};
  }

  function routePath(points) {
    return points.map((item, index) => `${index ? "L" : "M"} ${item.x.toFixed(1)} ${item.y.toFixed(1)}`).join(" ");
  }

  async function applyRouting() {
    if (running) return;
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    if (!stage || stage.dataset.transitionInputActionLabelsReady !== "true") return;
    running = true;
    try {
      const machine = await readMachine();
      if (!machine) return;
      const signature = [machine.name, machine.initial_state, stage.clientWidth, stage.clientHeight].join("\u001f");
      if (stage.dataset.initialTransitionRouting === signature) return;

      const svg = stage.querySelector(":scope > svg.edge-svg");
      const initialPath = svg?.querySelector(":scope > path:not(.state-transition-path)");
      const dot = stage.querySelector(".initial-dot");
      const target = [...stage.querySelectorAll(".state-node")].find(node => (
        node.querySelector(".state-name")?.textContent?.trim() === String(machine.initial_state)
      ));
      if (!svg || !initialPath || !dot || !target) return;

      stage.querySelectorAll(".state-node.initial-target").forEach(node => node.classList.remove("initial-target"));
      target.classList.add("initial-target");
      const targetRect = stageRect(target);
      const normalPaths = [...svg.querySelectorAll(":scope > path.state-transition-path")];
      const normalPolylines = normalPaths.map(path => sampleSvgPath(path));
      const nodeObstacles = [...stage.querySelectorAll(".state-node")]
        .filter(node => node !== target)
        .map(node => expanded(stageRect(node), NODE_CLEARANCE));
      const labelObstacles = [...stage.querySelectorAll(".edge-label.transition-label")]
        .map(label => expanded(stageRect(label), LABEL_CLEARANCE));
      const context = {
        width: stage.clientWidth,
        height: stage.clientHeight,
        nodeObstacles,
        labelObstacles,
        normalPolylines,
      };
      const ranked = candidateRoutes(targetRect)
        .map(candidate => scoreCandidate(candidate, context))
        .filter(Boolean)
        .sort((left, right) => left.score - right.score);
      if (!ranked.length) return;

      const best = ranked[0];
      initialPath.setAttribute("d", routePath(best.candidate.points));
      initialPath.classList.add("initial-transition-path");
      initialPath.dataset.routeSide = best.candidate.side;
      initialPath.dataset.routeCrossings = String(best.crossings);
      initialPath.dataset.routeClearance = best.minimum.toFixed(2);
      dot.style.left = `${best.candidate.dot.x - DOT_RADIUS}px`;
      dot.style.top = `${best.candidate.dot.y - DOT_RADIUS}px`;
      dot.dataset.routeSide = best.candidate.side;

      stage.dataset.initialTransitionRouting = signature;
      stage.dataset.initialRouteReady = "true";
      stage.dataset.initialRouteCrossings = String(best.crossings);
      stage.dataset.initialRouteClearance = best.minimum.toFixed(2);
      document.dispatchEvent(new CustomEvent("glyph-initial-transition-route-ready", {
        detail: {
          machine: machine.name,
          side: best.candidate.side,
          crossings: best.crossings,
          clearance: best.minimum,
          marker: MARKER,
        },
      }));
    } finally {
      running = false;
    }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(() => applyRouting().catch(error => {
      console.error("initial transition routing failed", error);
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


def enhance_initial_transition_html(html: str) -> str:
    """Route the initial pseudo-transition independently from normal transitions.

    The browser evaluates multiple dedicated entry ports around the initial state
    and chooses the shortest route that does not cross normal transitions, state
    nodes, or transition labels. The initial marker and path therefore remain a
    separate visual lane rather than sharing a normal transition endpoint.
    """

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
