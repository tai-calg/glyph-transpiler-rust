from __future__ import annotations


_MARKER = "glyph-layout-publication-certificate-v1"


_SCRIPT = r"""
<script id="glyph-layout-publication-certificate-v1-script">
(() => {
  const MARKER = "glyph-layout-publication-certificate-v1";
  const FRAME_BUDGET_MS = 8;
  const INITIAL_CLEARANCE = 5;
  const ROUTE_NODE_CLEARANCE = 1.5;
  const FOREIGN_LABEL_CLEARANCE = 1;
  let requestedGeneration = 0;
  let completedGeneration = 0;
  let running = false;
  let timer = null;
  let destroyed = false;

  const number = value => Number.parseFloat(value || "0") || 0;
  function geometry() {
    const value = window.glyphDiagramGeometry;
    if (!value || value.version < 1) throw Error("diagram geometry kernel is unavailable");
    return value;
  }
  function stageOf() {
    return document.querySelector(".state-node")?.closest(".graph-stage") || null;
  }
  function stageRect(element, margin = 0) {
    return {
      left: element.offsetLeft - margin,
      top: element.offsetTop - margin,
      right: element.offsetLeft + element.offsetWidth + margin,
      bottom: element.offsetTop + element.offsetHeight + margin,
    };
  }
  function centeredRect(element, margin = 0) {
    const rawLeft = element.style.left;
    const rawTop = element.style.top;
    const centerX = Number.parseFloat(rawLeft);
    const centerY = Number.parseFloat(rawTop);
    if (!rawLeft || !rawTop || !Number.isFinite(centerX) || !Number.isFinite(centerY)) {
      return stageRect(element, margin);
    }
    return {
      left: centerX - element.offsetWidth / 2 - margin,
      top: centerY - element.offsetHeight / 2 - margin,
      right: centerX + element.offsetWidth / 2 + margin,
      bottom: centerY + element.offsetHeight / 2 + margin,
    };
  }
  function nodeName(node) {
    return node.querySelector(".state-name,.node-name")?.textContent?.trim() || "";
  }
  function geometryFingerprint(stage) {
    const values = [
      MARKER,
      stage.dataset.diagramDigest || "source",
      stage.clientWidth,
      stage.clientHeight,
      stage.dataset.transitionLayoutGeneration || "0",
      stage.dataset.initialTransitionRouting || "",
    ];
    for (const node of stage.querySelectorAll(".state-node")) {
      values.push("node", nodeName(node), node.offsetLeft, node.offsetTop, node.offsetWidth, node.offsetHeight);
    }
    for (const path of stage.querySelectorAll(":scope > svg.edge-svg > path")) {
      values.push("path", path.dataset.transitionId || "initial", path.getAttribute("d") || "");
    }
    for (const cluster of stage.querySelectorAll(".transition-io-cluster")) {
      values.push(
        "label",
        cluster.dataset.transitionId || "",
        number(cluster.style.left),
        number(cluster.style.top),
        cluster.offsetWidth,
        cluster.offsetHeight,
        cluster.dataset.ioValue || "",
      );
    }
    return values.join("\u001f");
  }
  function fail(stage, violations, metrics) {
    stage.dataset.layoutCertificateState = "failed";
    stage.dataset.layoutCertificateViolations = JSON.stringify(violations);
    stage.dataset.layoutCertificateMetrics = JSON.stringify(metrics);
    stage.dataset.transitionPublicationReady = "false";
    document.dispatchEvent(new CustomEvent("glyph-layout-publication-certificate-failed", {
      detail: {marker: MARKER, violations, metrics},
    }));
  }

  async function audit(token) {
    const stage = stageOf();
    if (!stage) return;
    if (stage.dataset.transitionLayoutState !== "ready"
      || stage.dataset.initialRouteReady !== "true") return;
    const fingerprint = geometryFingerprint(stage);
    if (stage.dataset.layoutCertificateFingerprint === fingerprint
      && stage.dataset.layoutCertificateState === "valid") {
      stage.dataset.layoutCertificateCacheHit = "true";
      completedGeneration = token;
      return;
    }
    stage.dataset.layoutCertificateCacheHit = "false";
    stage.dataset.layoutCertificateState = "pending";
    const started = performance.now();
    const geom = geometry();
    const violations = [];
    const transactionAudit = window.glyphTransitionLayoutTransaction?.audit?.();
    if (!transactionAudit?.ok) {
      violations.push({kind: "transition-layout", details: transactionAudit || {missing: true}});
    }

    const svg = stage.querySelector(":scope > svg.edge-svg");
    const initial = svg?.querySelector(":scope > path.initial-transition-path");
    const normalPaths = [...(svg?.querySelectorAll(":scope > path.state-transition-path") || [])];
    if (!initial) {
      violations.push({kind: "initial-route", reason: "missing"});
    } else {
      const certificate = geom.verifyPathElement(initial, normalPaths, {
        tolerance: .35,
        maxSegmentLength: 3,
        minimumClearance: INITIAL_CLEARANCE,
      });
      if (!certificate.valid) {
        violations.push({
          kind: "initial-route",
          reason: "crossing-or-clearance",
          crossings: certificate.crossings,
          clearance: certificate.clearance,
        });
      }
    }

    const nodes = new Map([...stage.querySelectorAll(".state-node")].map(node => [nodeName(node), node]));
    const clusters = [...stage.querySelectorAll(".transition-io-cluster")];
    const tasks = [];
    normalPaths.forEach(path => {
      const id = path.dataset.transitionId || "";
      const source = path.dataset.sourceState || "";
      const target = path.dataset.targetState || "";
      const polyline = geom.flattenPathElement(path, {tolerance: .35, maxSegmentLength: 3});
      nodes.forEach((node, name) => {
        if (name === source || name === target) return;
        tasks.push(() => {
          if (geom.polylineHitsRect(polyline, stageRect(node, ROUTE_NODE_CLEARANCE))) {
            violations.push({kind: "route-node", transition: id, node: name});
          }
        });
      });
      clusters.forEach(cluster => {
        const labelId = cluster.dataset.transitionId || "";
        if (labelId === id) return;
        tasks.push(() => {
          if (geom.polylineHitsRect(polyline, centeredRect(cluster, FOREIGN_LABEL_CLEARANCE))) {
            violations.push({kind: "route-foreign-label", transition: id, label: labelId});
          }
        });
      });
    });
    const budget = await geom.runBudgeted(tasks, task => task(), {
      budgetMs: FRAME_BUDGET_MS,
      cancelled: () => token !== requestedGeneration || destroyed,
    });
    if (token !== requestedGeneration || destroyed) return;
    const metrics = {
      durationMs: performance.now() - started,
      maxSliceMs: budget.maxSliceMs,
      yields: budget.yields,
      tasks: tasks.length,
      paths: normalPaths.length + (initial ? 1 : 0),
      cacheHits: geom.statistics.pathCacheHits,
      cacheMisses: geom.statistics.pathCacheMisses,
    };
    stage.dataset.layoutCertificateDurationMs = metrics.durationMs.toFixed(2);
    stage.dataset.layoutCertificateMaxSliceMs = metrics.maxSliceMs.toFixed(2);
    stage.dataset.layoutCertificateYieldCount = String(metrics.yields);
    stage.dataset.layoutCertificateTaskCount = String(metrics.tasks);
    if (violations.length) {
      fail(stage, violations, metrics);
      completedGeneration = token;
      return;
    }
    stage.dataset.layoutCertificateFingerprint = fingerprint;
    stage.dataset.layoutCertificateState = "valid";
    stage.dataset.layoutCertificateVersion = "1";
    stage.dataset.layoutCertificateConstraints = "labels,nodes,tether,initial-route,foreign-route-obstacles";
    stage.dataset.layoutCertificateViolations = "[]";
    stage.dataset.layoutCertificateMetrics = JSON.stringify(metrics);
    completedGeneration = token;
    document.dispatchEvent(new CustomEvent("glyph-layout-publication-certificate-ready", {
      detail: {marker: MARKER, version: 1, fingerprint, metrics},
    }));
  }

  async function drain() {
    if (running || destroyed) return;
    running = true;
    try {
      while (!destroyed && completedGeneration < requestedGeneration) {
        const token = requestedGeneration;
        try {
          await audit(token);
          if (token === requestedGeneration) completedGeneration = token;
        } catch (error) {
          if (token !== requestedGeneration || destroyed) continue;
          const stage = stageOf();
          if (stage) fail(stage, [{kind: "certificate-error", message: String(error?.message || error)}], {});
          console.error("layout publication certification failed", error);
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
    const stage = stageOf();
    if (stage) {
      stage.dataset.layoutCertificateState = "pending";
      stage.dataset.layoutCertificateReason = reason;
    }
    clearTimeout(timer);
    timer = setTimeout(drain, delay);
    return requestedGeneration;
  }

  for (const eventName of [
    "glyph-transition-layout-transaction-ready",
    "glyph-initial-transition-route-ready",
    "glyph-execution-context-changed",
    "glyph-locale-changed",
  ]) {
    document.addEventListener(eventName, () => schedule(eventName, 0));
  }
  document.addEventListener("change", event => {
    if (event.target?.id === "machine-select") schedule("machine-change", 0);
  });
  for (const eventName of ["pagehide", "beforeunload"]) {
    window.addEventListener(eventName, () => {
      destroyed = true;
      clearTimeout(timer);
      requestedGeneration += 1;
    }, {once: true});
  }

  window.glyphLayoutPublicationCertificate = {
    marker: MARKER,
    version: 1,
    schedule,
    audit: () => audit(requestedGeneration),
    get generation() { return requestedGeneration; },
    get completedGeneration() { return completedGeneration; },
  };
  schedule("bootstrap", 0);
})();
</script>
"""


def enhance_layout_publication_certificate_html(html: str) -> str:
    """Certify final rendered geometry incrementally before publication."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
