from __future__ import annotations


_MARKER = "glyph-diagram-geometry-kernel-v1"


_SCRIPT = r"""
<script id="glyph-diagram-geometry-kernel-v1-script">
(() => {
  const MARKER = "glyph-diagram-geometry-kernel-v1";
  if (window.glyphDiagramGeometry?.marker === MARKER) return;

  const EPSILON = 0.001;
  const pathCache = new WeakMap();
  const statistics = {
    pathCacheHits: 0,
    pathCacheMisses: 0,
    flattenedPaths: 0,
  };

  const point = (x, y) => ({x: Number(x), y: Number(y)});
  const distance = (left, right) => Math.hypot(right.x - left.x, right.y - left.y);
  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));
  const orientation = (a, b, c) => (
    (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
  );
  const between = (value, first, second, tolerance = EPSILON) => (
    value >= Math.min(first, second) - tolerance
      && value <= Math.max(first, second) + tolerance
  );

  function segmentsIntersect(a, b, c, d, tolerance = EPSILON) {
    const abC = orientation(a, b, c);
    const abD = orientation(a, b, d);
    const cdA = orientation(c, d, a);
    const cdB = orientation(c, d, b);
    if (((abC > tolerance && abD < -tolerance) || (abC < -tolerance && abD > tolerance))
      && ((cdA > tolerance && cdB < -tolerance) || (cdA < -tolerance && cdB > tolerance))) {
      return true;
    }
    const collinear = (value, p, q, r) => Math.abs(value) <= tolerance
      && between(r.x, p.x, q.x, tolerance)
      && between(r.y, p.y, q.y, tolerance);
    return collinear(abC, a, b, c)
      || collinear(abD, a, b, d)
      || collinear(cdA, c, d, a)
      || collinear(cdB, c, d, b);
  }

  function pointSegmentDistance(value, start, end) {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const denominator = dx * dx + dy * dy;
    if (denominator <= EPSILON) return distance(value, start);
    const ratio = clamp(((value.x - start.x) * dx + (value.y - start.y) * dy) / denominator, 0, 1);
    return distance(value, point(start.x + dx * ratio, start.y + dy * ratio));
  }

  function segmentDistance(a, b, c, d) {
    if (segmentsIntersect(a, b, c, d)) return 0;
    return Math.min(
      pointSegmentDistance(a, c, d),
      pointSegmentDistance(b, c, d),
      pointSegmentDistance(c, a, b),
      pointSegmentDistance(d, a, b),
    );
  }

  function polylineSegments(polyline) {
    return polyline.slice(1).map((end, index) => [polyline[index], end]);
  }

  function crossingCount(polyline, obstacles) {
    let crossings = 0;
    const leftSegments = polylineSegments(polyline);
    for (const obstacle of obstacles) {
      const rightSegments = polylineSegments(obstacle);
      for (const [a, b] of leftSegments) {
        for (const [c, d] of rightSegments) {
          if (segmentsIntersect(a, b, c, d)) crossings += 1;
        }
      }
    }
    return crossings;
  }

  function minimumPolylineDistance(polyline, obstacles) {
    if (!obstacles.length) return 999;
    let minimum = Number.POSITIVE_INFINITY;
    const leftSegments = polylineSegments(polyline);
    for (const obstacle of obstacles) {
      const rightSegments = polylineSegments(obstacle);
      for (const [a, b] of leftSegments) {
        for (const [c, d] of rightSegments) {
          minimum = Math.min(minimum, segmentDistance(a, b, c, d));
          if (minimum <= 0) return 0;
        }
      }
    }
    return minimum;
  }

  function rectEdges(rect) {
    const topLeft = point(rect.left, rect.top);
    const topRight = point(rect.right, rect.top);
    const bottomRight = point(rect.right, rect.bottom);
    const bottomLeft = point(rect.left, rect.bottom);
    return [
      [topLeft, topRight],
      [topRight, bottomRight],
      [bottomRight, bottomLeft],
      [bottomLeft, topLeft],
    ];
  }

  function pointInsideRect(value, rect) {
    return value.x >= rect.left - EPSILON && value.x <= rect.right + EPSILON
      && value.y >= rect.top - EPSILON && value.y <= rect.bottom + EPSILON;
  }

  function polylineHitsRect(polyline, rect) {
    if (polyline.some(value => pointInsideRect(value, rect))) return true;
    const edges = rectEdges(rect);
    return polylineSegments(polyline).some(([a, b]) => (
      edges.some(([c, d]) => segmentsIntersect(a, b, c, d))
    ));
  }

  function tokenizePathData(data) {
    return String(data || "").match(/[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?/g) || [];
  }

  function pathSegments(data) {
    const tokens = tokenizePathData(data);
    const values = [];
    let index = 0;
    let command = null;
    let current = point(0, 0);
    let subpathStart = point(0, 0);
    const isCommand = value => /^[A-Za-z]$/.test(value || "");
    const number = () => {
      if (index >= tokens.length || isCommand(tokens[index])) throw Error("invalid SVG path data");
      return Number(tokens[index++]);
    };
    const absolutePoint = (x, y, relative) => relative
      ? point(current.x + x, current.y + y)
      : point(x, y);

    while (index < tokens.length) {
      if (isCommand(tokens[index])) command = tokens[index++];
      if (!command) throw Error("SVG path command is missing");
      const upper = command.toUpperCase();
      const relative = command !== upper;
      if (upper === "Z") {
        if (distance(current, subpathStart) > EPSILON) values.push({kind: "L", p0: current, p1: subpathStart});
        current = subpathStart;
        command = null;
        continue;
      }
      let firstMove = upper === "M";
      let consumed = false;
      while (index < tokens.length && !isCommand(tokens[index])) {
        consumed = true;
        if (upper === "M" || upper === "L") {
          const next = absolutePoint(number(), number(), relative);
          if (firstMove) {
            current = next;
            subpathStart = next;
            firstMove = false;
          } else {
            values.push({kind: "L", p0: current, p1: next});
            current = next;
          }
        } else if (upper === "H") {
          const x = number();
          const next = point(relative ? current.x + x : x, current.y);
          values.push({kind: "L", p0: current, p1: next});
          current = next;
        } else if (upper === "V") {
          const y = number();
          const next = point(current.x, relative ? current.y + y : y);
          values.push({kind: "L", p0: current, p1: next});
          current = next;
        } else if (upper === "Q") {
          const control = absolutePoint(number(), number(), relative);
          const next = absolutePoint(number(), number(), relative);
          values.push({kind: "Q", p0: current, p1: control, p2: next});
          current = next;
        } else if (upper === "C") {
          const first = absolutePoint(number(), number(), relative);
          const second = absolutePoint(number(), number(), relative);
          const next = absolutePoint(number(), number(), relative);
          values.push({kind: "C", p0: current, p1: first, p2: second, p3: next});
          current = next;
        } else {
          throw Error(`unsupported SVG path command: ${command}`);
        }
        if (upper === "M") command = relative ? "l" : "L";
      }
      if (!consumed && upper !== "Z") throw Error(`SVG path command has no arguments: ${command}`);
    }
    return values;
  }

  const midpoint = (a, b) => point((a.x + b.x) / 2, (a.y + b.y) / 2);
  function lineFlatness(control, start, end) {
    return pointSegmentDistance(control, start, end);
  }

  function flattenQuadratic(segment, output, options, depth = 0) {
    const {p0, p1, p2} = segment;
    if (depth >= options.maxDepth
      || (lineFlatness(p1, p0, p2) <= options.tolerance
        && distance(p0, p2) <= options.maxSegmentLength)) {
      output.push(p2);
      return;
    }
    const p01 = midpoint(p0, p1);
    const p12 = midpoint(p1, p2);
    const center = midpoint(p01, p12);
    flattenQuadratic({p0, p1: p01, p2: center}, output, options, depth + 1);
    flattenQuadratic({p0: center, p1: p12, p2}, output, options, depth + 1);
  }

  function flattenCubic(segment, output, options, depth = 0) {
    const {p0, p1, p2, p3} = segment;
    const flatness = Math.max(lineFlatness(p1, p0, p3), lineFlatness(p2, p0, p3));
    if (depth >= options.maxDepth
      || (flatness <= options.tolerance && distance(p0, p3) <= options.maxSegmentLength)) {
      output.push(p3);
      return;
    }
    const p01 = midpoint(p0, p1);
    const p12 = midpoint(p1, p2);
    const p23 = midpoint(p2, p3);
    const p012 = midpoint(p01, p12);
    const p123 = midpoint(p12, p23);
    const center = midpoint(p012, p123);
    flattenCubic({p0, p1: p01, p2: p012, p3: center}, output, options, depth + 1);
    flattenCubic({p0: center, p1: p123, p2: p23, p3}, output, options, depth + 1);
  }

  function flattenPathData(data, options = {}) {
    const settings = {
      tolerance: Number(options.tolerance ?? 0.35),
      maxSegmentLength: Number(options.maxSegmentLength ?? 3),
      maxDepth: Number(options.maxDepth ?? 14),
    };
    const segments = pathSegments(data);
    if (!segments.length) return [];
    const output = [segments[0].p0];
    for (const segment of segments) {
      if (segment.kind === "L") {
        const length = distance(segment.p0, segment.p1);
        const count = Math.max(1, Math.ceil(length / settings.maxSegmentLength));
        for (let item = 1; item <= count; item += 1) {
          const ratio = item / count;
          output.push(point(
            segment.p0.x + (segment.p1.x - segment.p0.x) * ratio,
            segment.p0.y + (segment.p1.y - segment.p0.y) * ratio,
          ));
        }
      } else if (segment.kind === "Q") {
        flattenQuadratic(segment, output, settings);
      } else if (segment.kind === "C") {
        flattenCubic(segment, output, settings);
      }
    }
    statistics.flattenedPaths += 1;
    return output;
  }

  function flattenPathElement(path, options = {}) {
    const data = path?.getAttribute?.("d") || "";
    const key = [data, options.tolerance ?? 0.35, options.maxSegmentLength ?? 3].join("\u001f");
    const cached = pathCache.get(path);
    if (cached?.key === key) {
      statistics.pathCacheHits += 1;
      return cached.points;
    }
    statistics.pathCacheMisses += 1;
    let points;
    try {
      points = flattenPathData(data, options);
    } catch {
      const length = path.getTotalLength();
      const step = Number(options.maxSegmentLength ?? 3);
      points = [];
      for (let offset = 0; offset < length; offset += step) {
        const value = path.getPointAtLength(offset);
        points.push(point(value.x, value.y));
      }
      const final = path.getPointAtLength(length);
      points.push(point(final.x, final.y));
    }
    pathCache.set(path, {key, points});
    return points;
  }

  function verifyPolyline(polyline, obstacles, options = {}) {
    const minimumClearance = Number(options.minimumClearance ?? 5);
    const crossings = crossingCount(polyline, obstacles);
    const clearance = minimumPolylineDistance(polyline, obstacles);
    return {
      valid: crossings === 0 && clearance + EPSILON >= minimumClearance,
      crossings,
      clearance,
      minimumClearance,
    };
  }

  function verifyPathData(data, obstacles, options = {}) {
    const polyline = flattenPathData(data, options);
    return {...verifyPolyline(polyline, obstacles, options), polyline};
  }

  function verifyPathElement(path, obstaclePaths, options = {}) {
    const polyline = flattenPathElement(path, options);
    const obstacles = obstaclePaths.map(item => flattenPathElement(item, options));
    return {...verifyPolyline(polyline, obstacles, options), polyline, obstacles};
  }

  async function runBudgeted(items, visitor, options = {}) {
    const budgetMs = Math.max(1, Number(options.budgetMs ?? 8));
    const cancelled = typeof options.cancelled === "function" ? options.cancelled : () => false;
    let sliceStarted = performance.now();
    const started = sliceStarted;
    let yields = 0;
    let maxSliceMs = 0;
    let visited = 0;
    for (let index = 0; index < items.length; index += 1) {
      if (cancelled()) return {cancelled: true, visited, yields, maxSliceMs, durationMs: performance.now() - started};
      await visitor(items[index], index);
      visited += 1;
      const elapsed = performance.now() - sliceStarted;
      maxSliceMs = Math.max(maxSliceMs, elapsed);
      if (elapsed >= budgetMs && index + 1 < items.length) {
        yields += 1;
        await new Promise(resolve => requestAnimationFrame(resolve));
        sliceStarted = performance.now();
      }
    }
    maxSliceMs = Math.max(maxSliceMs, performance.now() - sliceStarted);
    return {cancelled: false, visited, yields, maxSliceMs, durationMs: performance.now() - started};
  }

  async function findBudgeted(items, predicate, options = {}) {
    let match = null;
    const metrics = await runBudgeted(items, async (item, index) => {
      if (match !== null) return;
      const value = await predicate(item, index);
      if (value) match = value;
    }, {
      ...options,
      cancelled: () => match !== null || options.cancelled?.() === true,
    });
    return {...metrics, match};
  }

  window.glyphDiagramGeometry = Object.freeze({
    marker: MARKER,
    version: 1,
    epsilon: EPSILON,
    point,
    distance,
    segmentsIntersect,
    pointSegmentDistance,
    segmentDistance,
    crossingCount,
    minimumPolylineDistance,
    pointInsideRect,
    polylineHitsRect,
    flattenPathData,
    flattenPathElement,
    verifyPolyline,
    verifyPathData,
    verifyPathElement,
    runBudgeted,
    findBudgeted,
    statistics,
  });
  document.dispatchEvent(new CustomEvent("glyph-diagram-geometry-kernel-ready", {
    detail: {marker: MARKER, version: 1},
  }));
})();
</script>
"""


def enhance_diagram_geometry_kernel_html(html: str) -> str:
    """Install the shared, cached and budget-aware rendered-geometry kernel."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
