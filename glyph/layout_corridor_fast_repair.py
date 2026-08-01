from __future__ import annotations


_MARKER = "glyph-layout-corridor-fast-repair-v1"


_SCRIPT = r"""
<script id="glyph-layout-corridor-fast-repair-v1-script">
(() => {
  const MARKER = "glyph-layout-corridor-fast-repair-v1";
  const VERSION = 1;
  const NODE_CLEARANCE = 3;
  const INITIAL_CLEARANCE = 6;
  const LABEL_GAP = 3;
  const STAGE_MARGIN = 12;
  const LANE_START = 20;
  const LANE_STEP = 34;
  const MAX_LANES = 9;
  const PORT_OFFSETS = [-18, 0, 18];
  const MAX_ROUTE_STEPS = 24000;
  const MAX_LABEL_STEPS = 120000;
  const LABEL_OPTION_LIMIT = 96;
  const PATH_FRACTIONS = [.1, .18, .26, .34, .42, .5, .58, .66, .74, .82, .9];
  const NORMAL_OFFSETS = [0, 18, -18, 32, -32, 48, -48, 64, -64, 80, -80, 96, -96];

  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));
  const distance = (left, right) => Math.hypot(right.x - left.x, right.y - left.y);

  function geometry() {
    const value = window.glyphDiagramGeometry;
    if (!value || value.version < 1) throw Error("diagram geometry kernel is unavailable");
    return value;
  }

  function nodeName(node) {
    return node.querySelector(".state-name,.node-name")?.textContent?.trim() || "";
  }

  function nodeRect(node, margin = 0) {
    return {
      left: node.offsetLeft - margin,
      top: node.offsetTop - margin,
      right: node.offsetLeft + node.offsetWidth + margin,
      bottom: node.offsetTop + node.offsetHeight + margin,
    };
  }

  function centeredRect(element, center, margin = 0) {
    return {
      left: center.x - element.offsetWidth / 2 - margin,
      top: center.y - element.offsetHeight / 2 - margin,
      right: center.x + element.offsetWidth / 2 + margin,
      bottom: center.y + element.offsetHeight / 2 + margin,
    };
  }

  function rectsIntersect(left, right) {
    return !(left.right <= right.left
      || right.right <= left.left
      || left.bottom <= right.top
      || right.bottom <= left.top);
  }

  function insideStage(rect, stage) {
    return rect.left >= STAGE_MARGIN
      && rect.top >= STAGE_MARGIN
      && rect.right <= stage.clientWidth - STAGE_MARGIN
      && rect.bottom <= stage.clientHeight - STAGE_MARGIN;
  }

  function currentCenter(cluster) {
    const x = Number.parseFloat(cluster.style.left);
    const y = Number.parseFloat(cluster.style.top);
    if (Number.isFinite(x) && Number.isFinite(y)) return {x, y};
    return {
      x: cluster.offsetLeft + cluster.offsetWidth / 2,
      y: cluster.offsetTop + cluster.offsetHeight / 2,
    };
  }

  function routeLength(points) {
    return points.slice(1).reduce((total, point, index) => (
      total + distance(points[index], point)
    ), 0);
  }

  function routePath(points) {
    return points.map((point, index) => (
      `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`
    )).join(" ");
  }

  function routeInside(points, stage) {
    return points.every(point => (
      point.x >= STAGE_MARGIN
      && point.y >= STAGE_MARGIN
      && point.x <= stage.clientWidth - STAGE_MARGIN
      && point.y <= stage.clientHeight - STAGE_MARGIN
    ));
  }

  function pathSnapshot(path) {
    return {
      d: path.getAttribute("d") || "",
      route: path.dataset.layoutCorridorRoute,
      version: path.dataset.layoutCorridorRouteVersion,
      side: path.dataset.layoutCorridorSide,
      lane: path.dataset.layoutCorridorLane,
    };
  }

  function restorePath(path, snapshot) {
    path.setAttribute("d", snapshot.d);
    for (const [key, value] of [
      ["layoutCorridorRoute", snapshot.route],
      ["layoutCorridorRouteVersion", snapshot.version],
      ["layoutCorridorSide", snapshot.side],
      ["layoutCorridorLane", snapshot.lane],
    ]) {
      if (value === undefined) delete path.dataset[key];
      else path.dataset[key] = value;
    }
  }

  function clusterSnapshot(cluster) {
    return {
      left: cluster.style.left,
      top: cluster.style.top,
      anchorX: cluster.dataset.anchorX,
      anchorY: cluster.dataset.anchorY,
      anchorFraction: cluster.dataset.anchorFraction,
      ioDistance: cluster.dataset.ioDistance,
      layoutLocalRepair: cluster.dataset.layoutLocalRepair,
      layoutLocalRepairVersion: cluster.dataset.layoutLocalRepairVersion,
      layoutLocalRepairScope: cluster.dataset.layoutLocalRepairScope,
    };
  }

  function restoreCluster(cluster, snapshot) {
    cluster.style.left = snapshot.left;
    cluster.style.top = snapshot.top;
    for (const [key, value] of Object.entries(snapshot)) {
      if (key === "left" || key === "top") continue;
      if (value === undefined) delete cluster.dataset[key];
      else cluster.dataset[key] = value;
    }
  }

  function port(rect, side, offset, selfRole = 0) {
    const selfOffset = selfRole * 18;
    if (side === "top" || side === "bottom") {
      return {
        x: clamp(
          (rect.left + rect.right) / 2 + offset + selfOffset,
          rect.left + 8,
          rect.right - 8,
        ),
        y: side === "top" ? rect.top : rect.bottom,
      };
    }
    return {
      x: side === "left" ? rect.left : rect.right,
      y: clamp(
        (rect.top + rect.bottom) / 2 + offset + selfOffset,
        rect.top + 8,
        rect.bottom - 8,
      ),
    };
  }

  function corridorCoordinate(side, lane, stage) {
    const distanceFromEdge = LANE_START + lane * LANE_STEP;
    if (side === "top" || side === "left") return distanceFromEdge;
    return (side === "bottom" ? stage.clientHeight : stage.clientWidth) - distanceFromEdge;
  }

  function corridorPoints(sourceRect, targetRect, side, lane, offset, stage, sameNode) {
    const source = port(sourceRect, side, offset, sameNode ? -1 : 0);
    const target = port(targetRect, side, offset, sameNode ? 1 : 0);
    const corridor = corridorCoordinate(side, lane, stage);
    if (side === "top") {
      if (corridor >= Math.min(sourceRect.top, targetRect.top) - 10) return null;
      return [source, {x: source.x, y: corridor}, {x: target.x, y: corridor}, target];
    }
    if (side === "bottom") {
      if (corridor <= Math.max(sourceRect.bottom, targetRect.bottom) + 10) return null;
      return [source, {x: source.x, y: corridor}, {x: target.x, y: corridor}, target];
    }
    if (side === "left") {
      if (corridor >= Math.min(sourceRect.left, targetRect.left) - 10) return null;
      return [source, {x: corridor, y: source.y}, {x: corridor, y: target.y}, target];
    }
    if (corridor <= Math.max(sourceRect.right, targetRect.right) + 10) return null;
    return [source, {x: corridor, y: source.y}, {x: corridor, y: target.y}, target];
  }

  function directionalPenalty(sourceRect, targetRect, side) {
    const dx = (targetRect.left + targetRect.right - sourceRect.left - sourceRect.right) / 2;
    const dy = (targetRect.top + targetRect.bottom - sourceRect.top - targetRect.bottom) / 2;
    const horizontal = Math.abs(dx) >= Math.abs(dy);
    if (horizontal && (side === "top" || side === "bottom")) return 0;
    if (!horizontal && (side === "left" || side === "right")) return 0;
    return 80;
  }

  function candidateRoutes(entry, context) {
    const geom = geometry();
    const values = [];
    const sides = ["top", "right", "bottom", "left"];
    for (const side of sides) {
      for (let lane = 0; lane < MAX_LANES; lane += 1) {
        for (const offset of PORT_OFFSETS) {
          const points = corridorPoints(
            entry.sourceRect,
            entry.targetRect,
            side,
            lane,
            offset,
            context.stage,
            entry.source === entry.target,
          );
          if (!points || !routeInside(points, context.stage)) continue;
          if (context.nodes.some(item => (
            item.name !== entry.source
            && item.name !== entry.target
            && geom.polylineHitsRect(points, item.rect)
          ))) continue;
          if (context.initialPolyline.length) {
            const certificate = geom.verifyPolyline(points, [context.initialPolyline], {
              minimumClearance: INITIAL_CLEARANCE,
            });
            if (!certificate.valid) continue;
          }
          const laneKey = `${side}:${lane}`;
          values.push({
            points,
            data: routePath(points),
            side,
            lane,
            laneKey,
            score: routeLength(points)
              + directionalPenalty(entry.sourceRect, entry.targetRect, side)
              + lane * 8
              + Math.abs(offset) * .15,
          });
        }
      }
    }
    values.sort((left, right) => left.score - right.score
      || left.side.localeCompare(right.side)
      || left.lane - right.lane);
    return values;
  }

  function assignRoutes(entries) {
    const ordered = [...entries].sort((left, right) => (
      left.candidates.length - right.candidates.length
      || left.id.localeCompare(right.id)
    ));
    const usedLanes = new Set();
    const assignment = new Map();
    let steps = 0;

    function visit(index) {
      steps += 1;
      if (steps > MAX_ROUTE_STEPS) return false;
      if (index >= ordered.length) return true;
      const entry = ordered[index];
      for (const candidate of entry.candidates) {
        if (usedLanes.has(candidate.laneKey)) continue;
        usedLanes.add(candidate.laneKey);
        assignment.set(entry.id, candidate);
        if (visit(index + 1)) return true;
        assignment.delete(entry.id);
        usedLanes.delete(candidate.laneKey);
      }
      return false;
    }

    return {
      assignment: visit(0) ? assignment : null,
      steps,
      ordered: ordered.map(entry => ({id: entry.id, candidates: entry.candidates.length})),
    };
  }

  function terminalFailure(message, details) {
    const error = Error(message);
    error.code = "layout-corridor-fast-repair-failed";
    error.details = JSON.stringify(details);
    return error;
  }

  function routeEntries(stage) {
    const geom = geometry();
    const paths = [...stage.querySelectorAll(
      ":scope > svg.edge-svg > path.state-transition-path",
    )];
    const nodes = new Map([...stage.querySelectorAll(".state-node")].map(node => (
      [nodeName(node), node]
    )));
    const nodeObstacles = [...nodes.entries()].map(([name, node]) => ({
      name,
      rect: nodeRect(node, NODE_CLEARANCE),
    }));
    const initial = stage.querySelector(
      ":scope > svg.edge-svg > path.initial-transition-path",
    );
    const initialPolyline = initial
      ? geom.flattenPathElement(initial, {tolerance: .35, maxSegmentLength: 3})
      : [];
    const entries = paths.map((path, index) => {
      const id = path.dataset.transitionId || `route-${index}`;
      const source = path.dataset.sourceState || "";
      const target = path.dataset.targetState || "";
      const sourceNode = nodes.get(source);
      const targetNode = nodes.get(target);
      if (!sourceNode || !targetNode) {
        throw terminalFailure("transition route endpoint is missing", {id, source, target});
      }
      return {
        id,
        path,
        source,
        target,
        sourceRect: nodeRect(sourceNode),
        targetRect: nodeRect(targetNode),
        candidates: [],
      };
    });
    const context = {stage, nodes: nodeObstacles, initialPolyline};
    for (const entry of entries) entry.candidates = candidateRoutes(entry, context);
    const empty = entries.filter(entry => !entry.candidates.length).map(entry => entry.id);
    if (empty.length) {
      throw terminalFailure("no certified outer route candidate exists", {empty});
    }
    const solved = assignRoutes(entries);
    if (!solved.assignment) {
      throw terminalFailure("outer route lanes have no joint assignment", {
        steps: solved.steps,
        entries: solved.ordered,
      });
    }
    for (const entry of entries) {
      const route = solved.assignment.get(entry.id);
      entry.path.setAttribute("d", route.data);
      entry.path.dataset.layoutCorridorRoute = "true";
      entry.path.dataset.layoutCorridorRouteVersion = String(VERSION);
      entry.path.dataset.layoutCorridorSide = route.side;
      entry.path.dataset.layoutCorridorLane = String(route.lane);
    }
    return {
      entries,
      metrics: {
        paths: entries.length,
        steps: solved.steps,
        lanes: [...solved.assignment.values()].map(item => item.laneKey),
      },
    };
  }

  function pathGeometry(stage) {
    const geom = geometry();
    return [...stage.querySelectorAll(
      ":scope > svg.edge-svg > path.state-transition-path",
    )].map(path => ({
      id: path.dataset.transitionId || "",
      path,
      points: geom.flattenPathElement(path, {tolerance: .35, maxSegmentLength: 3}),
    }));
  }

  function labelCandidates(entry, context) {
    const geom = geometry();
    const values = [];
    const seen = new Set();
    let length = 0;
    try {
      length = entry.path.getTotalLength();
    } catch {
      return values;
    }
    if (!(length > 0)) return values;
    for (const fraction of PATH_FRACTIONS) {
      const offset = length * fraction;
      const anchor = entry.path.getPointAtLength(offset);
      const before = entry.path.getPointAtLength(Math.max(0, offset - 2));
      const after = entry.path.getPointAtLength(Math.min(length, offset + 2));
      const tangentLength = Math.max(1, Math.hypot(after.x - before.x, after.y - before.y));
      const normal = {
        x: -(after.y - before.y) / tangentLength,
        y: (after.x - before.x) / tangentLength,
      };
      for (const normalOffset of NORMAL_OFFSETS) {
        const center = {
          x: anchor.x + normal.x * normalOffset,
          y: anchor.y + normal.y * normalOffset,
        };
        const key = `${Math.round(center.x * 10)}:${Math.round(center.y * 10)}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const rect = centeredRect(entry.cluster, center, LABEL_GAP);
        if (!insideStage(rect, context.stage)) continue;
        if (context.nodes.some(node => rectsIntersect(rect, node))) continue;
        if (context.fixedLabels.some(label => rectsIntersect(rect, label))) continue;
        if (context.paths.some(path => (
          path.id !== entry.id && geom.polylineHitsRect(path.points, rect)
        ))) continue;
        values.push({
          center,
          anchor: {x: anchor.x, y: anchor.y},
          anchorFraction: fraction,
          rect,
          score: distance(center, entry.current)
            + Math.abs(normalOffset) * .04
            + Math.abs(fraction - .5) * 4,
        });
      }
    }
    values.sort((left, right) => left.score - right.score
      || left.center.y - right.center.y
      || left.center.x - right.center.x);
    return values.slice(0, LABEL_OPTION_LIMIT);
  }

  function assignLabels(entries) {
    const assignment = new Map();
    const placed = [];
    const remaining = new Set(entries);
    let steps = 0;

    function visit() {
      steps += 1;
      if (steps > MAX_LABEL_STEPS) return false;
      if (!remaining.size) return true;
      let selected = null;
      let viable = null;
      for (const entry of remaining) {
        const options = entry.options.filter(option => (
          !placed.some(rect => rectsIntersect(option.rect, rect))
        ));
        if (!options.length) return false;
        if (!viable || options.length < viable.length
          || (options.length === viable.length && entry.id.localeCompare(selected.id) < 0)) {
          selected = entry;
          viable = options;
        }
      }
      remaining.delete(selected);
      for (const option of viable) {
        assignment.set(selected.id, option);
        placed.push(option.rect);
        if (visit()) return true;
        placed.pop();
        assignment.delete(selected.id);
      }
      remaining.add(selected);
      return false;
    }

    return {assignment: visit() ? assignment : null, steps};
  }

  function placeLabels(stage) {
    const paths = pathGeometry(stage);
    const pathById = new Map(paths.map(item => [item.id, item]));
    const clusters = [...stage.querySelectorAll(".transition-io-cluster")];
    const fixedLabels = clusters
      .filter(cluster => cluster.dataset.manualIo === "true")
      .map(cluster => centeredRect(cluster, currentCenter(cluster), LABEL_GAP));
    const context = {
      stage,
      paths,
      nodes: [...stage.querySelectorAll(".state-node")].map(node => nodeRect(node, NODE_CLEARANCE)),
      fixedLabels,
    };
    const entries = clusters
      .filter(cluster => cluster.dataset.manualIo !== "true")
      .map(cluster => {
        const id = cluster.dataset.transitionId || "";
        const path = pathById.get(id)?.path;
        if (!path) throw terminalFailure("transition label route is missing", {id});
        return {id, cluster, path, current: currentCenter(cluster), options: []};
      });
    for (const entry of entries) entry.options = labelCandidates(entry, context);
    const empty = entries.filter(entry => !entry.options.length).map(entry => entry.id);
    if (empty.length) {
      throw terminalFailure("corridor route has no certified label position", {empty});
    }
    const solved = assignLabels(entries);
    if (!solved.assignment) {
      throw terminalFailure("corridor labels have no joint assignment", {
        steps: solved.steps,
        entries: entries.map(entry => ({id: entry.id, options: entry.options.length})),
      });
    }
    const moved = [];
    for (const entry of entries) {
      const option = solved.assignment.get(entry.id);
      if (distance(entry.current, option.center) > .25) moved.push(entry.id);
      entry.cluster.style.left = `${option.center.x}px`;
      entry.cluster.style.top = `${option.center.y}px`;
      entry.cluster.dataset.anchorX = String(option.anchor.x);
      entry.cluster.dataset.anchorY = String(option.anchor.y);
      entry.cluster.dataset.anchorFraction = String(option.anchorFraction);
      entry.cluster.dataset.ioDistance = String(distance(option.center, option.anchor));
      entry.cluster.dataset.layoutLocalRepair = "true";
      entry.cluster.dataset.layoutLocalRepairVersion = "4";
      entry.cluster.dataset.layoutLocalRepairScope = "corridor-fast-reroute";
    }
    return {labels: entries.length, moved, steps: solved.steps};
  }

  function dirtyLabelIds(violations) {
    return [...new Set((violations || [])
      .filter(item => item?.kind === "route-foreign-label")
      .map(item => String(item.label || ""))
      .filter(Boolean))];
  }

  function hasManualConflict(stage, violations) {
    const dirty = new Set(dirtyLabelIds(violations));
    return [...stage.querySelectorAll(".transition-io-cluster")].some(cluster => (
      dirty.has(cluster.dataset.transitionId || "")
      && cluster.dataset.manualIo === "true"
    ));
  }

  function shouldPreempt(stage, violations) {
    if (hasManualConflict(stage, violations)) return false;
    const paths = stage.querySelectorAll(
      ":scope > svg.edge-svg > path.state-transition-path",
    ).length;
    const dirty = dirtyLabelIds(violations).length;
    return paths >= 8 && dirty >= Math.max(4, Math.ceil(paths / 2));
  }

  async function corridorRepair(stage, violations, options = {}) {
    if (options.cancelled?.()) throw new DOMException("stale corridor repair", "AbortError");
    const paths = [...stage.querySelectorAll(
      ":scope > svg.edge-svg > path.state-transition-path",
    )];
    const clusters = [...stage.querySelectorAll(".transition-io-cluster")];
    const pathSnapshots = new Map(paths.map(path => [path, pathSnapshot(path)]));
    const clusterSnapshots = new Map(clusters.map(cluster => [cluster, clusterSnapshot(cluster)]));
    const started = performance.now();
    try {
      const routed = routeEntries(stage);
      if (options.cancelled?.()) throw new DOMException("stale corridor repair", "AbortError");
      const labels = placeLabels(stage);
      if (options.cancelled?.()) throw new DOMException("stale corridor repair", "AbortError");
      const audit = window.glyphTransitionLayoutTransaction?.audit?.();
      if (audit && !audit.ok) {
        throw terminalFailure("corridor placement failed transaction audit", {
          violations: audit.violations,
        });
      }
      const metrics = {
        durationMs: performance.now() - started,
        route: routed.metrics,
        labels,
      };
      stage.dataset.layoutCorridorFastRepairState = "repaired";
      stage.dataset.layoutCorridorFastRepairVersion = String(VERSION);
      stage.dataset.layoutCorridorFastRepairMetrics = JSON.stringify(metrics);
      stage.dataset.layoutLocalRepairState = "repaired";
      stage.dataset.layoutLocalRepairScope = "corridor-fast-reroute";
      stage.dataset.layoutLocalRepairLabels = labels.moved.join(",");
      document.dispatchEvent(new CustomEvent("glyph-layout-corridor-fast-repair-ready", {
        detail: {marker: MARKER, version: VERSION, metrics},
      }));
      return {
        repaired: true,
        labels: labels.moved,
        dirtyLabels: dirtyLabelIds(violations),
        scope: "corridor-fast-reroute",
        corridorRerouted: true,
        metrics,
      };
    } catch (error) {
      for (const [path, snapshot] of pathSnapshots) restorePath(path, snapshot);
      for (const [cluster, snapshot] of clusterSnapshots) restoreCluster(cluster, snapshot);
      for (const key of [
        "layoutCorridorFastRepairState",
        "layoutCorridorFastRepairVersion",
        "layoutCorridorFastRepairMetrics",
      ]) delete stage.dataset[key];
      throw error;
    }
  }

  const base = window.glyphLayoutLocalRepair;
  if (!base || base.version < 3 || typeof base.repair !== "function") {
    console.error("layout corridor fast repair requires corridor repair v1");
    return;
  }
  const baseRepair = base.repair.bind(base);
  base.repair = async (stage, violations, options = {}) => {
    if (shouldPreempt(stage, violations)) {
      return corridorRepair(stage, violations, options);
    }
    return baseRepair(stage, violations, options);
  };
  base.version = 4;
  base.fastCorridorMarker = MARKER;
})();
</script>
"""


def enhance_layout_corridor_fast_repair_html(html: str) -> str:
    """Preempt dense collisions with bounded certified route and label repair."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
