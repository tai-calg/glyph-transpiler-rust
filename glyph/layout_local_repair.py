from __future__ import annotations


_MARKER = "glyph-layout-local-repair-v1"


_SCRIPT = r"""
<script id="glyph-layout-local-repair-v1-script">
(() => {
  const MARKER = "glyph-layout-local-repair-v1";
  const FRAME_BUDGET_MS = 8;
  const MAX_STEPS = 80000;
  const OPTION_LIMIT = 140;
  const LABEL_GAP = 2;
  const NODE_GAP = 2;
  const RINGS = [0, 10, 20, 30, 40, 52, 64, 76, 88, 96];
  const ANGLES = 72;
  let generation = 0;

  const number = value => Number.parseFloat(value || "0") || 0;
  const distance = (left, right) => Math.hypot(right.x - left.x, right.y - left.y);
  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));

  function geometry() {
    const value = window.glyphDiagramGeometry;
    if (!value || value.version < 1) throw Error("diagram geometry kernel is unavailable");
    return value;
  }

  function centeredRect(element, center, margin = 0) {
    return {
      left: center.x - element.offsetWidth / 2 - margin,
      top: center.y - element.offsetHeight / 2 - margin,
      right: center.x + element.offsetWidth / 2 + margin,
      bottom: center.y + element.offsetHeight / 2 + margin,
    };
  }

  function nodeRect(node, margin = 0) {
    return {
      left: node.offsetLeft - margin,
      top: node.offsetTop - margin,
      right: node.offsetLeft + node.offsetWidth + margin,
      bottom: node.offsetTop + node.offsetHeight + margin,
    };
  }

  function rectsIntersect(left, right) {
    return !(left.right <= right.left
      || right.right <= left.left
      || left.bottom <= right.top
      || right.bottom <= left.top);
  }

  function insideStage(rect, stage) {
    return rect.left >= 8 && rect.top >= 8
      && rect.right <= stage.clientWidth - 8
      && rect.bottom <= stage.clientHeight - 8;
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

  function anchorOf(cluster) {
    const x = Number.parseFloat(cluster.dataset.anchorX);
    const y = Number.parseFloat(cluster.dataset.anchorY);
    return Number.isFinite(x) && Number.isFinite(y) ? {x, y} : currentCenter(cluster);
  }

  function candidateCenters(entry, stage) {
    const values = [];
    const seen = new Set();
    const maxDistance = Math.max(0, number(entry.cluster.dataset.maxIoDistance) || 96);
    const add = raw => {
      const dx = raw.x - entry.anchor.x;
      const dy = raw.y - entry.anchor.y;
      const length = Math.hypot(dx, dy);
      const ratio = length > maxDistance && length > 0 ? maxDistance / length : 1;
      const projected = {
        x: entry.anchor.x + dx * ratio,
        y: entry.anchor.y + dy * ratio,
      };
      const halfWidth = entry.cluster.offsetWidth / 2 + 8;
      const halfHeight = entry.cluster.offsetHeight / 2 + 8;
      const center = {
        x: clamp(projected.x, halfWidth, stage.clientWidth - halfWidth),
        y: clamp(projected.y, halfHeight, stage.clientHeight - halfHeight),
      };
      if (distance(center, entry.anchor) > maxDistance + .25) return;
      const key = `${Math.round(center.x * 10)}:${Math.round(center.y * 10)}`;
      if (!seen.has(key)) {
        seen.add(key);
        values.push(center);
      }
    };
    add(entry.current);
    for (const radius of RINGS) {
      if (radius > maxDistance + .25) continue;
      for (let index = 0; index < ANGLES; index += 1) {
        const angle = index * 2 * Math.PI / ANGLES;
        add({
          x: entry.anchor.x + Math.cos(angle) * radius,
          y: entry.anchor.y + Math.sin(angle) * radius,
        });
      }
    }
    return values;
  }

  function pathGeometry(stage) {
    const geom = geometry();
    const paths = [...stage.querySelectorAll(":scope > svg.edge-svg > path")];
    return paths.map(path => ({
      id: path.classList.contains("initial-transition-path")
        ? "__initial__"
        : path.dataset.transitionId || "",
      points: geom.flattenPathElement(path, {tolerance: .35, maxSegmentLength: 3}),
    }));
  }

  async function buildOptions(entry, context, token) {
    const geom = geometry();
    const candidates = candidateCenters(entry, context.stage);
    const values = [];
    const metrics = await geom.runBudgeted(candidates, center => {
      const rect = centeredRect(entry.cluster, center, LABEL_GAP);
      if (!insideStage(rect, context.stage)) return;
      if (context.nodes.some(node => rectsIntersect(rect, node))) return;
      if (context.fixedLabels.some(label => rectsIntersect(rect, label.rect))) return;
      if (context.paths.some(path => path.id !== entry.id && geom.polylineHitsRect(path.points, rect))) return;
      const displacement = distance(center, entry.current);
      const anchorDistance = distance(center, entry.anchor);
      const displacementWeight = entry.dirty ? 1 : 12;
      values.push({
        center,
        rect,
        score: displacement * displacementWeight + anchorDistance * .03,
      });
    }, {
      budgetMs: FRAME_BUDGET_MS,
      cancelled: () => token !== generation,
    });
    values.sort((left, right) => left.score - right.score
      || left.center.y - right.center.y
      || left.center.x - right.center.x);
    return {options: values.slice(0, OPTION_LIMIT), metrics};
  }

  function terminalFailure(message, details) {
    const error = Error(message);
    error.code = "layout-local-repair-failed";
    error.details = JSON.stringify(details);
    return error;
  }

  async function solve(entries, token) {
    const assignment = new Map();
    const placed = [];
    const remaining = new Set(entries);
    let steps = 0;
    let yields = 0;
    let maxSliceMs = 0;
    let sliceStarted = performance.now();

    async function checkpoint() {
      steps += 1;
      if (steps > MAX_STEPS) throw terminalFailure("local repair search budget exceeded", {steps});
      if (token !== generation) throw new DOMException("stale layout repair", "AbortError");
      const elapsed = performance.now() - sliceStarted;
      maxSliceMs = Math.max(maxSliceMs, elapsed);
      if (elapsed >= FRAME_BUDGET_MS) {
        yields += 1;
        await new Promise(resolve => requestAnimationFrame(resolve));
        sliceStarted = performance.now();
      }
    }

    async function visit() {
      await checkpoint();
      if (!remaining.size) return true;
      let selected = null;
      let viable = null;
      for (const entry of remaining) {
        const options = entry.options.filter(option => (
          !placed.some(rect => rectsIntersect(option.rect, rect))
        ));
        if (!options.length) return false;
        if (!viable || options.length < viable.length
          || (options.length === viable.length && entry.options.length < selected.options.length)) {
          selected = entry;
          viable = options;
        }
      }
      remaining.delete(selected);
      for (const option of viable) {
        assignment.set(selected.id, option);
        placed.push(option.rect);
        if (await visit()) return true;
        placed.pop();
        assignment.delete(selected.id);
        await checkpoint();
      }
      remaining.add(selected);
      return false;
    }

    const solved = await visit();
    maxSliceMs = Math.max(maxSliceMs, performance.now() - sliceStarted);
    return {assignment: solved ? assignment : null, steps, yields, maxSliceMs};
  }

  function makeEntry(id, cluster, dirtySet) {
    return {
      id,
      cluster,
      current: currentCenter(cluster),
      anchor: anchorOf(cluster),
      manual: cluster.dataset.manualIo === "true",
      dirty: dirtySet.has(id),
      options: [],
    };
  }

  function fixedLabelRects(clusters, movableIds) {
    return [...clusters.entries()]
      .filter(([id]) => !movableIds.has(id))
      .map(([id, cluster]) => ({
        id,
        rect: centeredRect(cluster, currentCenter(cluster), LABEL_GAP),
      }));
  }

  async function buildPlan(stage, clusters, ids, dirtySet, token, scope) {
    const movableIds = new Set(ids);
    const entries = ids.map(id => {
      const cluster = clusters.get(id);
      if (!cluster) throw terminalFailure("dirty transition label is missing", {id, scope});
      return makeEntry(id, cluster, dirtySet);
    });
    const context = {
      stage,
      nodes: [...stage.querySelectorAll(".state-node")].map(node => nodeRect(node, NODE_GAP)),
      fixedLabels: fixedLabelRects(clusters, movableIds),
      paths: pathGeometry(stage),
    };
    let optionYields = 0;
    let optionMaxSliceMs = 0;
    const emptyEntries = [];
    for (const entry of entries) {
      const built = await buildOptions(entry, context, token);
      if (token !== generation) throw new DOMException("stale layout repair", "AbortError");
      entry.options = built.options;
      optionYields += built.metrics.yields;
      optionMaxSliceMs = Math.max(optionMaxSliceMs, built.metrics.maxSliceMs);
      if (!entry.options.length) emptyEntries.push(entry.id);
    }
    if (emptyEntries.length) {
      return {
        scope,
        entries,
        assignment: null,
        reason: "empty-options",
        details: {emptyEntries},
        optionYields,
        optionMaxSliceMs,
        searchYields: 0,
        searchMaxSliceMs: 0,
        steps: 0,
      };
    }
    const solved = await solve(entries, token);
    return {
      scope,
      entries,
      assignment: solved.assignment,
      reason: solved.assignment ? "solved" : "no-joint-solution",
      details: solved.assignment ? {} : {
        entries: entries.map(entry => ({id: entry.id, options: entry.options.length})),
        steps: solved.steps,
      },
      optionYields,
      optionMaxSliceMs,
      searchYields: solved.yields,
      searchMaxSliceMs: solved.maxSliceMs,
      steps: solved.steps,
    };
  }

  async function repair(stage, violations, options = {}) {
    generation += 1;
    const token = generation;
    const started = performance.now();
    const dirtyIds = [...new Set((violations || [])
      .filter(item => item?.kind === "route-foreign-label")
      .map(item => String(item.label || ""))
      .filter(Boolean))];
    if (!dirtyIds.length) return {repaired: false, reason: "no-repairable-violations"};

    const clusters = new Map([...stage.querySelectorAll(".transition-io-cluster")]
      .map(cluster => [cluster.dataset.transitionId || "", cluster]));
    const dirtySet = new Set(dirtyIds);
    const manualConflicts = dirtyIds.filter(id => clusters.get(id)?.dataset.manualIo === "true");
    if (manualConflicts.length) {
      throw terminalFailure("manual label positions violate publication geometry", {manualConflicts});
    }

    let plan = await buildPlan(stage, clusters, dirtyIds, dirtySet, token, "dirty-only");
    let fallback = null;
    if (!plan.assignment) {
      const globalIds = [...clusters.entries()]
        .filter(([, cluster]) => cluster.dataset.manualIo !== "true")
        .map(([id]) => id);
      fallback = {
        from: plan.scope,
        reason: plan.reason,
        details: plan.details,
      };
      plan = await buildPlan(stage, clusters, globalIds, dirtySet, token, "global-movable");
    }
    if (!plan.assignment) {
      throw terminalFailure("no adaptive local repair satisfies publication geometry", {
        scope: plan.scope,
        reason: plan.reason,
        details: plan.details,
        fallback,
      });
    }

    const moved = [];
    for (const entry of plan.entries) {
      const option = plan.assignment.get(entry.id);
      if (!option) continue;
      if (distance(option.center, entry.current) > .25) moved.push(entry.id);
      entry.cluster.style.left = `${option.center.x}px`;
      entry.cluster.style.top = `${option.center.y}px`;
      entry.cluster.dataset.ioDistance = String(distance(option.center, entry.anchor));
      entry.cluster.dataset.layoutLocalRepair = "true";
      entry.cluster.dataset.layoutLocalRepairVersion = "1";
      entry.cluster.dataset.layoutLocalRepairScope = plan.scope;
    }
    const metrics = {
      durationMs: performance.now() - started,
      optionYields: plan.optionYields,
      searchYields: plan.searchYields,
      maxSliceMs: Math.max(plan.optionMaxSliceMs, plan.searchMaxSliceMs),
      steps: plan.steps,
      labels: plan.entries.length,
      dirtyLabels: dirtyIds.length,
      movedLabels: moved.length,
      scope: plan.scope,
      fallback,
    };
    stage.dataset.layoutLocalRepairState = "repaired";
    stage.dataset.layoutLocalRepairScope = plan.scope;
    stage.dataset.layoutLocalRepairLabels = moved.join(",");
    stage.dataset.layoutLocalRepairDirtyLabels = dirtyIds.join(",");
    stage.dataset.layoutLocalRepairMetrics = JSON.stringify(metrics);
    document.dispatchEvent(new CustomEvent("glyph-layout-local-repair-ready", {
      detail: {marker: MARKER, labels: moved, dirtyLabels: dirtyIds, scope: plan.scope, metrics},
    }));
    return {repaired: true, labels: moved, dirtyLabels: dirtyIds, scope: plan.scope, metrics};
  }

  window.glyphLayoutLocalRepair = {
    marker: MARKER,
    version: 1,
    repair,
    get generation() { return generation; },
  };
})();
</script>
"""


def enhance_layout_local_repair_html(html: str) -> str:
    """Install a frame-budgeted adaptive repair solver for label geometry."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
