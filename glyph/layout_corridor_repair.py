from __future__ import annotations


_MARKER = "glyph-layout-corridor-repair-v1"


_SCRIPT = r"""
<script id="glyph-layout-corridor-repair-v1-script">
(() => {
  const MARKER = "glyph-layout-corridor-repair-v1";
  const VERSION = 1;
  const NODE_CLEARANCE = 3;
  const INITIAL_CLEARANCE = 6;
  const STAGE_MARGIN = 12;
  const LANE_START = 20;
  const LANE_STEP = 20;
  const MAX_LANES = 9;
  const PORT_OFFSETS = [-28, -14, 0, 14, 28];
  const MAX_ASSIGNMENT_STEPS = 24000;

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
      anchorX: cluster.dataset.anchorX,
      anchorY: cluster.dataset.anchorY,
      anchorFraction: cluster.dataset.anchorFraction,
    };
  }

  function restoreCluster(cluster, snapshot) {
    for (const [key, value] of Object.entries(snapshot)) {
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
    const dy = (targetRect.top + targetRect.bottom - sourceRect.top - sourceRect.bottom) / 2;
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
          const foreignNodeHit = context.nodes.some(item => (
            item.name !== entry.source
            && item.name !== entry.target
            && geom.polylineHitsRect(points, item.rect)
          ));
          if (foreignNodeHit) continue;
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
      if (steps > MAX_ASSIGNMENT_STEPS) return false;
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
    error.code = "layout-corridor-repair-failed";
    error.details = JSON.stringify(details);
    return error;
  }

  function reroute(stage) {
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
    const context = {
      stage,
      nodes: nodeObstacles,
      initialPolyline,
    };
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
      const escaped = window.CSS?.escape
        ? CSS.escape(entry.id)
        : entry.id.replace(/[^A-Za-z0-9_-]/g, "\\$&");
      const cluster = stage.querySelector(
        `.transition-io-cluster[data-transition-id="${escaped}"]`,
      );
      if (cluster && typeof entry.path.getTotalLength === "function") {
        const point = entry.path.getPointAtLength(entry.path.getTotalLength() * .5);
        cluster.dataset.anchorX = String(point.x);
        cluster.dataset.anchorY = String(point.y);
        cluster.dataset.anchorFraction = ".5";
      }
    }
    stage.dataset.layoutCorridorRepairState = "routed";
    stage.dataset.layoutCorridorRepairVersion = String(VERSION);
    stage.dataset.layoutCorridorRepairPathCount = String(entries.length);
    stage.dataset.layoutCorridorRepairAssignmentSteps = String(solved.steps);
    return {
      paths: entries.length,
      steps: solved.steps,
      lanes: [...solved.assignment.values()].map(item => item.laneKey),
    };
  }

  function shouldEscalate(error) {
    if (error?.code !== "layout-local-repair-failed") return false;
    try {
      const details = JSON.parse(String(error?.details || "{}"));
      if (Array.isArray(details.manualConflicts) && details.manualConflicts.length) return false;
      return details.reason === "empty-options"
        || details.reason === "no-joint-solution"
        || details.scope === "global-movable";
    } catch {
      return false;
    }
  }

  const base = window.glyphLayoutLocalRepair;
  if (!base || base.version < 2 || typeof base.repair !== "function") {
    console.error("layout corridor repair requires local repair v2");
    return;
  }
  const baseRepair = base.repair.bind(base);
  base.repair = async (stage, violations, options = {}) => {
    try {
      return await baseRepair(stage, violations, options);
    } catch (error) {
      if (!shouldEscalate(error)) throw error;
      const paths = [...stage.querySelectorAll(
        ":scope > svg.edge-svg > path.state-transition-path",
      )];
      const clusters = [...stage.querySelectorAll(".transition-io-cluster")];
      const pathSnapshots = new Map(paths.map(path => [path, pathSnapshot(path)]));
      const clusterSnapshots = new Map(clusters.map(cluster => [cluster, clusterSnapshot(cluster)]));
      let routeMetrics = null;
      try {
        routeMetrics = reroute(stage);
        const repaired = await baseRepair(stage, violations, options);
        if (!repaired?.repaired) {
          throw terminalFailure("local repair did not commit after rerouting", {
            routeMetrics,
            result: repaired || null,
          });
        }
        repaired.metrics = {
          ...(repaired.metrics || {}),
          corridorReroute: routeMetrics,
        };
        repaired.corridorRerouted = true;
        document.dispatchEvent(new CustomEvent("glyph-layout-corridor-repair-ready", {
          detail: {marker: MARKER, version: VERSION, metrics: routeMetrics},
        }));
        return repaired;
      } catch (rerouteError) {
        for (const [path, snapshot] of pathSnapshots) restorePath(path, snapshot);
        for (const [cluster, snapshot] of clusterSnapshots) restoreCluster(cluster, snapshot);
        delete stage.dataset.layoutCorridorRepairState;
        delete stage.dataset.layoutCorridorRepairVersion;
        delete stage.dataset.layoutCorridorRepairPathCount;
        delete stage.dataset.layoutCorridorRepairAssignmentSteps;
        if (rerouteError?.code === "layout-corridor-repair-failed") throw rerouteError;
        throw terminalFailure("outer route escalation did not restore publication geometry", {
          routeMetrics,
          cause: String(rerouteError?.message || rerouteError),
          details: String(rerouteError?.details || ""),
        });
      }
    }
  };
  base.version = 3;
  base.corridorMarker = MARKER;
})();
</script>
"""


def enhance_layout_corridor_repair_html(html: str) -> str:
    """Escalate unsatisfied dense layouts to certified outer-route repair."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
