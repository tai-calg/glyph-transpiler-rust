from __future__ import annotations


_MARKER = "glyph-layout-shelf-repair-v1"


_SCRIPT = r"""
<script id="glyph-layout-shelf-repair-v1-script">
(() => {
  const MARKER = "glyph-layout-shelf-repair-v1";
  const VERSION = 1;
  const STAGE_MARGIN = 12;
  const NODE_CLEARANCE = 4;
  const LABEL_CLEARANCE = 2;
  const INITIAL_CLEARANCE = 6;
  const GRID_CLEARANCE = 14;
  const SHELF_GAP = 30;
  const PORT_OFFSETS = [-.3, -.15, 0, .15, .3];

  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));
  const pointKey = point => `${point.x.toFixed(1)}:${point.y.toFixed(1)}`;
  const distance = (left, right) => Math.hypot(right.x - left.x, right.y - left.y);

  function geometry() {
    const value = window.glyphDiagramGeometry;
    if (!value || value.version < 1) throw Error("diagram geometry kernel is unavailable");
    return value;
  }

  function nodeName(node) {
    return node.querySelector(".state-name,.node-name")?.textContent?.trim() || "";
  }

  function rect(element, margin = 0) {
    return {
      left: element.offsetLeft - margin,
      top: element.offsetTop - margin,
      right: element.offsetLeft + element.offsetWidth + margin,
      bottom: element.offsetTop + element.offsetHeight + margin,
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

  function insideStage(point, stage) {
    return point.x >= STAGE_MARGIN && point.y >= STAGE_MARGIN
      && point.x <= stage.clientWidth - STAGE_MARGIN
      && point.y <= stage.clientHeight - STAGE_MARGIN;
  }

  function routePath(points) {
    return points.map((point, index) => (
      `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`
    )).join(" ");
  }

  function pathSnapshot(path) {
    return {
      d: path.getAttribute("d") || "",
      shelf: path.dataset.layoutShelfRoute,
      version: path.dataset.layoutShelfRouteVersion,
      row: path.dataset.layoutShelfRow,
      column: path.dataset.layoutShelfColumn,
    };
  }

  function restorePath(path, snapshot) {
    path.setAttribute("d", snapshot.d);
    for (const [key, value] of [
      ["layoutShelfRoute", snapshot.shelf],
      ["layoutShelfRouteVersion", snapshot.version],
      ["layoutShelfRow", snapshot.row],
      ["layoutShelfColumn", snapshot.column],
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

  function terminalFailure(message, details) {
    const error = Error(message);
    error.code = "layout-shelf-repair-failed";
    error.details = JSON.stringify(details);
    return error;
  }

  function dirtyLabelIds(violations) {
    return [...new Set((violations || [])
      .filter(item => item?.kind === "route-foreign-label")
      .map(item => String(item.label || ""))
      .filter(Boolean))];
  }

  function shouldPreempt(stage, violations) {
    const dirty = new Set(dirtyLabelIds(violations));
    if ([...stage.querySelectorAll(".transition-io-cluster")].some(cluster => (
      dirty.has(cluster.dataset.transitionId || "")
      && cluster.dataset.manualIo === "true"
    ))) return false;
    const pathCount = stage.querySelectorAll(
      ":scope > svg.edge-svg > path.state-transition-path",
    ).length;
    return pathCount >= 8 && dirty.size >= Math.max(4, Math.ceil(pathCount / 2));
  }

  function shelfLayout(stage, clusters) {
    const oldWidth = stage.clientWidth;
    const oldHeight = stage.clientHeight;
    const maximumWidth = Math.max(108, ...clusters.map(cluster => cluster.offsetWidth));
    const maximumHeight = Math.max(28, ...clusters.map(cluster => cluster.offsetHeight));
    const columns = clusters.length >= 8 ? 2 : 1;
    const rows = Math.ceil(clusters.length / columns);
    const bayWidth = maximumWidth + 44;
    const rowGap = maximumHeight + 20;
    const shelfLeft = oldWidth + 40;
    const shelfTop = oldHeight + 40;
    const width = shelfLeft + columns * bayWidth + (columns - 1) * SHELF_GAP + 40;
    const height = shelfTop + rows * rowGap + 40;
    stage.style.width = `${Math.ceil(width)}px`;
    stage.style.height = `${Math.ceil(height)}px`;
    return clusters.map((cluster, index) => {
      const column = index % columns;
      const row = Math.floor(index / columns);
      const left = shelfLeft + column * (bayWidth + SHELF_GAP);
      const right = left + bayWidth;
      const y = shelfTop + row * rowGap + rowGap / 2;
      return {
        id: cluster.dataset.transitionId || `label-${index}`,
        cluster,
        column,
        row,
        entry: {x: left, y},
        exit: {x: right, y},
        center: {x: (left + right) / 2, y},
      };
    });
  }

  function nodePorts(node) {
    const bounds = rect(node);
    const width = bounds.right - bounds.left;
    const height = bounds.bottom - bounds.top;
    const ports = [];
    for (const offset of PORT_OFFSETS) {
      ports.push({x: bounds.left + width * (.5 + offset), y: bounds.top});
      ports.push({x: bounds.left + width * (.5 + offset), y: bounds.bottom});
      ports.push({x: bounds.left, y: bounds.top + height * (.5 + offset)});
      ports.push({x: bounds.right, y: bounds.top + height * (.5 + offset)});
    }
    return ports;
  }

  function uniqueSorted(values, minimum, maximum) {
    return [...new Set(values
      .map(value => Math.round(clamp(value, minimum, maximum) * 10) / 10))]
      .sort((left, right) => left - right);
  }

  function segmentAllowed(left, right, context) {
    if (left.x !== right.x && left.y !== right.y) return false;
    if (!insideStage(left, context.stage) || !insideStage(right, context.stage)) return false;
    const geom = geometry();
    const points = [left, right];
    if (context.nodeObstacles.some(obstacle => geom.polylineHitsRect(points, obstacle))) return false;
    if (context.labelObstacles.some(obstacle => geom.polylineHitsRect(points, obstacle))) return false;
    if (context.initialPolyline.length) {
      const certificate = geom.verifyPolyline(points, [context.initialPolyline], {
        minimumClearance: INITIAL_CLEARANCE,
      });
      if (!certificate.valid) return false;
    }
    return true;
  }

  function shortestGridPath(starts, goal, context) {
    const xValues = uniqueSorted([
      STAGE_MARGIN,
      context.stage.clientWidth - STAGE_MARGIN,
      goal.x,
      ...starts.map(point => point.x),
      ...context.nodeObstacles.flatMap(item => [item.left - GRID_CLEARANCE, item.right + GRID_CLEARANCE]),
      ...context.labelObstacles.flatMap(item => [item.left - GRID_CLEARANCE, item.right + GRID_CLEARANCE]),
    ], STAGE_MARGIN, context.stage.clientWidth - STAGE_MARGIN);
    const yValues = uniqueSorted([
      STAGE_MARGIN,
      context.stage.clientHeight - STAGE_MARGIN,
      goal.y,
      ...starts.map(point => point.y),
      ...context.nodeObstacles.flatMap(item => [item.top - GRID_CLEARANCE, item.bottom + GRID_CLEARANCE]),
      ...context.labelObstacles.flatMap(item => [item.top - GRID_CLEARANCE, item.bottom + GRID_CLEARANCE]),
    ], STAGE_MARGIN, context.stage.clientHeight - STAGE_MARGIN);
    const byKey = new Map();
    for (const x of xValues) {
      for (const y of yValues) {
        const point = {x, y};
        byKey.set(pointKey(point), point);
      }
    }
    for (const start of starts) byKey.set(pointKey(start), start);
    byKey.set(pointKey(goal), goal);
    const all = [...byKey.values()];
    const adjacent = new Map(all.map(point => [pointKey(point), []]));
    const connectLine = line => {
      line.sort((left, right) => left.x - right.x || left.y - right.y);
      for (let index = 1; index < line.length; index += 1) {
        const left = line[index - 1];
        const right = line[index];
        if (!segmentAllowed(left, right, context)) continue;
        const weight = distance(left, right);
        adjacent.get(pointKey(left)).push({point: right, weight});
        adjacent.get(pointKey(right)).push({point: left, weight});
      }
    };
    for (const y of yValues) connectLine(all.filter(point => point.y === y));
    for (const x of xValues) connectLine(all.filter(point => point.x === x));

    const distances = new Map(all.map(point => [pointKey(point), Number.POSITIVE_INFINITY]));
    const previous = new Map();
    const unvisited = new Set(all.map(pointKey));
    for (const start of starts) {
      const key = pointKey(start);
      distances.set(key, 0);
      previous.set(key, null);
    }
    const goalKey = pointKey(goal);
    while (unvisited.size) {
      let currentKey = null;
      let currentDistance = Number.POSITIVE_INFINITY;
      for (const key of unvisited) {
        const value = distances.get(key);
        if (value < currentDistance) {
          currentDistance = value;
          currentKey = key;
        }
      }
      if (currentKey === null || !Number.isFinite(currentDistance)) break;
      unvisited.delete(currentKey);
      if (currentKey === goalKey) break;
      for (const edge of adjacent.get(currentKey) || []) {
        const nextKey = pointKey(edge.point);
        if (!unvisited.has(nextKey)) continue;
        const candidate = currentDistance + edge.weight;
        if (candidate < distances.get(nextKey)) {
          distances.set(nextKey, candidate);
          previous.set(nextKey, currentKey);
        }
      }
    }
    if (!Number.isFinite(distances.get(goalKey))) return null;
    const result = [];
    let key = goalKey;
    while (key !== null && key !== undefined) {
      result.push(byKey.get(key));
      key = previous.get(key);
    }
    result.reverse();
    return result;
  }

  function compress(points) {
    const result = [];
    for (const point of points) {
      const previous = result[result.length - 1];
      const before = result[result.length - 2];
      if (previous && point.x === previous.x && point.y === previous.y) continue;
      if (before && previous
        && ((before.x === previous.x && previous.x === point.x)
          || (before.y === previous.y && previous.y === point.y))) {
        result[result.length - 1] = point;
      } else {
        result.push(point);
      }
    }
    return result;
  }

  function routeTransition(stage, path, sourceNode, targetNode, bay, allBays, nodes, initialPolyline) {
    const id = path.dataset.transitionId || bay.id;
    const labelObstacles = allBays
      .filter(item => item.id !== id)
      .map(item => centeredRect(item.cluster, item.center, LABEL_CLEARANCE));
    const nodeObstacles = nodes
      .filter(item => item.node !== sourceNode && item.node !== targetNode)
      .map(item => rect(item.node, NODE_CLEARANCE));
    const context = {stage, nodeObstacles, labelObstacles, initialPolyline};
    const sourcePath = shortestGridPath(nodePorts(sourceNode), bay.entry, context);
    const targetPath = shortestGridPath(nodePorts(targetNode), bay.exit, context);
    if (!sourcePath || !targetPath) {
      throw terminalFailure("no obstacle-free shelf route exists", {
        id,
        source: nodeName(sourceNode),
        target: nodeName(targetNode),
        sourcePath: Boolean(sourcePath),
        targetPath: Boolean(targetPath),
      });
    }
    const points = compress([
      ...sourcePath,
      bay.exit,
      ...[...targetPath].reverse().slice(1),
    ]);
    path.setAttribute("d", routePath(points));
    path.dataset.layoutShelfRoute = "true";
    path.dataset.layoutShelfRouteVersion = String(VERSION);
    path.dataset.layoutShelfRow = String(bay.row);
    path.dataset.layoutShelfColumn = String(bay.column);
    bay.cluster.style.left = `${bay.center.x}px`;
    bay.cluster.style.top = `${bay.center.y}px`;
    bay.cluster.dataset.anchorX = String(bay.center.x);
    bay.cluster.dataset.anchorY = String(bay.center.y);
    bay.cluster.dataset.anchorFraction = ".5";
    bay.cluster.dataset.ioDistance = "0";
    bay.cluster.dataset.layoutLocalRepair = "true";
    bay.cluster.dataset.layoutLocalRepairVersion = "5";
    bay.cluster.dataset.layoutLocalRepairScope = "shelf-reroute";
  }

  async function repair(stage, violations, options = {}) {
    if (options.cancelled?.()) throw new DOMException("stale shelf repair", "AbortError");
    const paths = [...stage.querySelectorAll(
      ":scope > svg.edge-svg > path.state-transition-path",
    )];
    const clusters = [...stage.querySelectorAll(".transition-io-cluster")]
      .sort((left, right) => (
        String(left.dataset.transitionId || "").localeCompare(String(right.dataset.transitionId || ""))
      ));
    const stageSnapshot = {width: stage.style.width, height: stage.style.height};
    const pathSnapshots = new Map(paths.map(path => [path, pathSnapshot(path)]));
    const clusterSnapshots = new Map(clusters.map(cluster => [cluster, clusterSnapshot(cluster)]));
    const started = performance.now();
    try {
      const bays = shelfLayout(stage, clusters);
      const bayById = new Map(bays.map(bay => [bay.id, bay]));
      const nodes = [...stage.querySelectorAll(".state-node")].map(node => ({
        name: nodeName(node),
        node,
      }));
      const nodeByName = new Map(nodes.map(item => [item.name, item.node]));
      const initial = stage.querySelector(
        ":scope > svg.edge-svg > path.initial-transition-path",
      );
      const initialPolyline = initial
        ? geometry().flattenPathElement(initial, {tolerance: .35, maxSegmentLength: 3})
        : [];
      for (const path of paths) {
        if (options.cancelled?.()) throw new DOMException("stale shelf repair", "AbortError");
        const id = path.dataset.transitionId || "";
        const sourceNode = nodeByName.get(path.dataset.sourceState || "");
        const targetNode = nodeByName.get(path.dataset.targetState || "");
        const bay = bayById.get(id);
        if (!sourceNode || !targetNode || !bay) {
          throw terminalFailure("shelf route binding is incomplete", {
            id,
            source: path.dataset.sourceState || "",
            target: path.dataset.targetState || "",
            bay: Boolean(bay),
          });
        }
        routeTransition(stage, path, sourceNode, targetNode, bay, bays, nodes, initialPolyline);
      }
      const audit = window.glyphTransitionLayoutTransaction?.audit?.();
      if (audit && !audit.ok) {
        throw terminalFailure("shelf placement failed transaction audit", {
          violations: audit.violations,
        });
      }
      const metrics = {
        durationMs: performance.now() - started,
        paths: paths.length,
        labels: clusters.length,
        width: stage.clientWidth,
        height: stage.clientHeight,
      };
      stage.dataset.layoutShelfRepairState = "repaired";
      stage.dataset.layoutShelfRepairVersion = String(VERSION);
      stage.dataset.layoutShelfRepairMetrics = JSON.stringify(metrics);
      stage.dataset.layoutLocalRepairState = "repaired";
      stage.dataset.layoutLocalRepairScope = "shelf-reroute";
      stage.dataset.layoutLocalRepairLabels = clusters
        .map(cluster => cluster.dataset.transitionId || "")
        .join(",");
      document.dispatchEvent(new CustomEvent("glyph-layout-shelf-repair-ready", {
        detail: {marker: MARKER, version: VERSION, metrics},
      }));
      return {
        repaired: true,
        labels: clusters.map(cluster => cluster.dataset.transitionId || ""),
        dirtyLabels: dirtyLabelIds(violations),
        scope: "shelf-reroute",
        shelfRerouted: true,
        metrics,
      };
    } catch (error) {
      stage.style.width = stageSnapshot.width;
      stage.style.height = stageSnapshot.height;
      for (const [path, snapshot] of pathSnapshots) restorePath(path, snapshot);
      for (const [cluster, snapshot] of clusterSnapshots) restoreCluster(cluster, snapshot);
      for (const key of [
        "layoutShelfRepairState",
        "layoutShelfRepairVersion",
        "layoutShelfRepairMetrics",
      ]) delete stage.dataset[key];
      throw error;
    }
  }

  const base = window.glyphLayoutLocalRepair;
  if (!base || base.version < 4 || typeof base.repair !== "function") {
    console.error("layout shelf repair requires fast corridor repair v1");
    return;
  }
  const baseRepair = base.repair.bind(base);
  base.repair = async (stage, violations, options = {}) => {
    if (shouldPreempt(stage, violations)) return repair(stage, violations, options);
    return baseRepair(stage, violations, options);
  };
  base.version = 5;
  base.shelfMarker = MARKER;
})();
</script>
"""


def enhance_layout_shelf_repair_html(html: str) -> str:
    """Route dense transitions through dedicated certified label shelves."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
