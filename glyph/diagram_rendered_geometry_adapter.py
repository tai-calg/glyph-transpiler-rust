from __future__ import annotations


_MARKER = "glyph-diagram-rendered-geometry-adapter-v1"


_SCRIPT = r"""
<script id="glyph-diagram-rendered-geometry-adapter-v1-script">
(() => {
  const MARKER = "glyph-diagram-rendered-geometry-adapter-v1";
  if (window.glyphDiagramRenderedGeometryAdapter?.marker === MARKER) return;

  const base = window.glyphDiagramGeometry;
  if (!base || base.version < 1) {
    throw Error("diagram geometry kernel is unavailable");
  }

  const renderedPathCache = new WeakMap();
  const point = (x, y) => ({x: Number(x), y: Number(y)});

  function flattenRenderedPathElement(path, options = {}) {
    if (!path || typeof path.getTotalLength !== "function"
      || typeof path.getPointAtLength !== "function") {
      return base.flattenPathElement(path, options);
    }

    const step = Math.max(0.5, Number(options.maxSegmentLength ?? 3));
    const key = [
      path.getAttribute?.("d") || "",
      path.getAttribute?.("transform") || "",
      step,
    ].join("\u001f");
    const cached = renderedPathCache.get(path);
    if (cached?.key === key) {
      base.statistics.pathCacheHits += 1;
      return cached.points;
    }

    base.statistics.pathCacheMisses += 1;
    let length;
    try {
      length = Number(path.getTotalLength());
    } catch {
      return base.flattenPathElement(path, options);
    }
    if (!Number.isFinite(length) || length < 0) {
      return base.flattenPathElement(path, options);
    }

    const points = [];
    if (length === 0) {
      const value = path.getPointAtLength(0);
      points.push(point(value.x, value.y));
    } else {
      for (let offset = 0; offset < length; offset += step) {
        const value = path.getPointAtLength(offset);
        points.push(point(value.x, value.y));
      }
      const final = path.getPointAtLength(length);
      points.push(point(final.x, final.y));
    }

    base.statistics.flattenedPaths += 1;
    renderedPathCache.set(path, {key, points});
    return points;
  }

  function verifyRenderedPathElement(path, obstaclePaths, options = {}) {
    const polyline = flattenRenderedPathElement(path, options);
    const obstacles = obstaclePaths.map(item => flattenRenderedPathElement(item, options));
    return {
      ...base.verifyPolyline(polyline, obstacles, options),
      polyline,
      obstacles,
      sampling: "svg-native-arclength",
    };
  }

  window.glyphDiagramGeometry = Object.freeze({
    ...base,
    version: Math.max(2, Number(base.version || 1)),
    renderedPathSampling: true,
    flattenPathElement: flattenRenderedPathElement,
    verifyPathElement: verifyRenderedPathElement,
  });

  window.glyphDiagramRenderedGeometryAdapter = Object.freeze({
    marker: MARKER,
    version: 1,
    flattenPathElement: flattenRenderedPathElement,
    verifyPathElement: verifyRenderedPathElement,
  });

  document.dispatchEvent(new CustomEvent("glyph-diagram-rendered-geometry-ready", {
    detail: {marker: MARKER, version: 1},
  }));
})();
</script>
"""


def enhance_diagram_rendered_geometry_html(html: str) -> str:
    """Use browser-native SVG arc-length sampling for final rendered geometry."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
