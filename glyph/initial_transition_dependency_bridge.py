from __future__ import annotations


_MARKER = "glyph-initial-transition-dependency-bridge-v2"


_SCRIPT = r"""
<script id="glyph-initial-transition-dependency-bridge-v2-script">
(() => {
  const MARKER = "glyph-initial-transition-dependency-bridge-v2";
  if (window.glyphInitialTransitionDependencyBridge?.marker === MARKER) return;

  let observedSvg = null;
  let routeObserver = null;
  let viewObserver = null;
  let bindTimer = null;
  let destroyed = false;
  let lastSignature = "";
  let settleGeneration = 0;

  function currentStage() {
    return document.querySelector(".state-node")?.closest(".graph-stage") || null;
  }

  function currentSvg() {
    return currentStage()?.querySelector(":scope > svg.edge-svg") || null;
  }

  function layoutGeneration(stage = currentStage()) {
    return String(stage?.dataset.transitionLayoutGeneration || "0");
  }

  function normalPaths(svg) {
    return [...(svg?.querySelectorAll(":scope > path.state-transition-path") || [])];
  }

  function geometrySignature(svg) {
    return normalPaths(svg).map((path, index) => [
      index,
      path.dataset.transitionId || "",
      path.getAttribute("class") || "",
      path.getAttribute("d") || "",
      path.getAttribute("transform") || "",
    ].join("\u001e")).join("\u001f");
  }

  function hasNormalPath(node) {
    return node?.nodeType === 1 && (
      node.matches?.("path.state-transition-path")
      || Boolean(node.querySelector?.("path.state-transition-path"))
    );
  }

  function classPreviouslyMarked(record) {
    return record.attributeName === "class"
      && String(record.oldValue || "").split(/\s+/).includes("state-transition-path");
  }

  function relevantMutation(record) {
    if (record.type === "attributes") {
      const target = record.target;
      return target?.nodeType === 1
        && target.tagName?.toLowerCase() === "path"
        && (target.matches?.(".state-transition-path") || classPreviouslyMarked(record));
    }
    if (record.type === "childList") {
      return [...record.addedNodes, ...record.removedNodes].some(hasNormalPath);
    }
    return false;
  }

  function nextFrame() {
    return new Promise(resolve => requestAnimationFrame(() => resolve()));
  }

  function router() {
    const value = window.glyphInitialTransitionRouter;
    return value?.version >= 2 ? value : null;
  }

  function invalidateCurrentGeneration(stage, reason) {
    if (!stage) return;
    const generation = layoutGeneration(stage);
    stage.dataset.initialRouteLayoutGeneration = generation;
    stage.dataset.initialRouteCertificate = "pending";
    stage.dataset.initialRouteReady = "pending";
    stage.dataset.initialRouteReason = reason;
    stage.dataset.transitionPublicationReady = "false";
    stage.dataset.layoutCertificateRequestState = "invalidated";
    delete stage.dataset.initialTransitionRouting;
  }

  function protocolFailureDetails(stage) {
    const selected = document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent?.trim() || "";
    const machines = typeof snapshot === "object" && snapshot?.views?.state?.machines || [];
    const machine = machines.find(item => item.name === selected) || machines[0] || null;
    return {
      selectedMachine: selected,
      initialState: machine?.initial_state ?? null,
      stateNames: [...(stage?.querySelectorAll(".state-name") || [])]
        .map(node => node.textContent?.trim() || ""),
      labelsReady: stage?.dataset.transitionInputActionLabelsReady || "",
      layoutGeneration: layoutGeneration(stage),
      routeLayoutGeneration: stage?.dataset.initialRouteLayoutGeneration || "",
      routeProtocolState: stage?.dataset.initialRouteProtocolState || "",
      routeProtocolReason: stage?.dataset.initialRouteProtocolReason || "",
      routeProtocolSequence: stage?.dataset.initialRouteProtocolSequence || "",
      routerGeneration: router()?.generation ?? null,
      routerCompletedGeneration: router()?.completedGeneration ?? null,
      routerProtocol: router()?.layoutGenerationProtocol || "",
      routerScheduleName: router()?.schedule?.name || "",
      routerScheduleSource: String(router()?.schedule || "").slice(0, 240),
      hasSvg: Boolean(currentSvg()),
      hasInitialPath: Boolean(currentSvg()?.querySelector(":scope > path:not(.state-transition-path)")),
      hasInitialDot: Boolean(stage?.querySelector(".initial-dot")),
    };
  }

  function markProtocolFailure(stage, state, reason) {
    if (!stage) return;
    const details = protocolFailureDetails(stage);
    stage.dataset.initialRouteReady = "failed";
    stage.dataset.initialRouteCertificate = "failed";
    stage.dataset.initialRouteError = reason;
    stage.dataset.initialRouteFailureDetails = JSON.stringify(details);
    stage.dataset.initialRouteSettleState = state;
    stage.dataset.transitionPublicationReady = "false";
    stage.dataset.layoutCertificateState = "failed";
    stage.dataset.layoutCertificateRequestState = "failed";
    stage.dataset.layoutCertificateReason = "initial-route-protocol-failed";
    stage.dataset.layoutCertificateViolations = JSON.stringify([{kind: state, reason, details}]);
  }

  function scheduleRouter(reason) {
    settleGeneration += 1;
    const stage = currentStage();
    invalidateCurrentGeneration(stage, reason);
    const value = router();
    if (!value) return false;
    value.schedule(reason, 0);
    return true;
  }

  function invalidateIfChanged(reason) {
    if (destroyed) return false;
    const svg = currentSvg();
    if (!svg) {
      scheduleBind();
      return false;
    }
    if (svg !== observedSvg) bind();
    const next = geometrySignature(svg);
    if (next === lastSignature) return false;
    lastSignature = next;
    return scheduleRouter(reason);
  }

  async function settleCertifiedRoute(event) {
    if (destroyed || event?.detail?.stable === true) return;
    const stage = currentStage();
    const svg = currentSvg();
    const initial = svg?.querySelector(":scope > path.initial-transition-path");
    if (!stage || !svg || !initial || stage.dataset.initialRouteCertificate !== "valid") return;

    const generation = layoutGeneration(stage);
    const eventGeneration = String(event?.detail?.layoutGeneration || generation);
    if (eventGeneration !== generation) return;
    stage.dataset.initialRouteLayoutGeneration = generation;

    const token = ++settleGeneration;
    const before = geometrySignature(svg);
    stage.dataset.initialRouteReady = "settling";
    stage.dataset.initialRouteSettleState = "waiting";
    stage.dataset.transitionPublicationReady = "false";

    await nextFrame();
    await nextFrame();
    if (destroyed || token !== settleGeneration) return;

    const finalStage = currentStage();
    const finalSvg = currentSvg();
    const after = geometrySignature(finalSvg);
    if (finalStage !== stage
      || finalSvg !== svg
      || layoutGeneration(finalStage) !== generation
      || before !== after) {
      stage.dataset.initialRouteSettleState = "geometry-changed";
      scheduleRouter("normal-route-not-quiescent");
      return;
    }

    const geom = window.glyphDiagramGeometry;
    const normals = normalPaths(finalSvg);
    if (!geom?.verifyPathElement) {
      stage.dataset.initialRouteSettleState = "geometry-kernel-missing";
      scheduleRouter("route-stability-kernel-missing");
      return;
    }
    const certificate = geom.verifyPathElement(initial, normals, {
      tolerance: .35,
      maxSegmentLength: 3,
      minimumClearance: 5,
    });
    if (!certificate.valid) {
      stage.dataset.initialRouteSettleState = "certificate-invalid";
      stage.dataset.initialRouteSettleDetails = JSON.stringify(certificate);
      scheduleRouter("post-route-stability-failed");
      return;
    }

    initial.dataset.routeCrossings = String(certificate.crossings);
    initial.dataset.routeClearance = Number(certificate.clearance).toFixed(2);
    initial.dataset.routeCertificate = "valid";
    stage.dataset.initialRouteCrossings = String(certificate.crossings);
    stage.dataset.initialRouteClearance = Number(certificate.clearance).toFixed(2);
    stage.dataset.initialRouteCertificate = "valid";
    stage.dataset.initialRouteSettleState = "stable";
    stage.dataset.initialRouteReady = "certified";
    stage.dataset.initialRouteLayoutGeneration = generation;
    lastSignature = after;

    const detail = {
      ...(event?.detail || {}),
      marker: MARKER,
      stable: true,
      layoutGeneration: generation,
      crossings: certificate.crossings,
      clearance: certificate.clearance,
    };
    window.glyphLayoutPublicationCertificate?.schedule?.(
      "glyph-initial-transition-route-ready",
      0,
    );
    document.dispatchEvent(new CustomEvent("glyph-initial-transition-route-ready", {
      detail,
    }));
  }

  function bind() {
    if (destroyed) return;
    clearTimeout(bindTimer);
    bindTimer = null;
    const svg = currentSvg();
    if (svg === observedSvg) return;
    settleGeneration += 1;
    routeObserver?.disconnect();
    routeObserver = null;
    observedSvg = svg;
    lastSignature = geometrySignature(svg);
    if (!svg) return;
    routeObserver = new MutationObserver(records => {
      if (!records.some(relevantMutation)) return;
      queueMicrotask(() => invalidateIfChanged("normal-route-geometry-changed"));
    });
    routeObserver.observe(svg, {
      attributes: true,
      attributeOldValue: true,
      attributeFilter: ["class", "d", "transform"],
      childList: true,
      subtree: true,
    });
  }

  function scheduleBind() {
    if (destroyed) return;
    clearTimeout(bindTimer);
    bindTimer = setTimeout(bind, 0);
  }

  document.addEventListener("glyph-initial-transition-route-ready", event => {
    settleCertifiedRoute(event).catch(error => {
      if (destroyed || error?.name === "AbortError") return;
      const stage = currentStage();
      if (stage) {
        stage.dataset.initialRouteSettleState = "failed";
        stage.dataset.initialRouteSettleDetails = String(error?.message || error);
      }
      scheduleRouter("route-stability-error");
    });
  });

  for (const eventName of [
    "glyph-diagram-geometry-kernel-ready",
    "glyph-uml-transition-ready",
  ]) {
    document.addEventListener(eventName, scheduleBind);
  }
  document.addEventListener("glyph-transition-layout-transaction-ready", event => {
    scheduleBind();
    const stage = currentStage();
    const generation = String(event?.detail?.generation || layoutGeneration(stage));
    setTimeout(() => {
      const current = currentStage();
      if (destroyed
        || current !== stage
        || layoutGeneration(current) !== generation
        || current?.dataset.transitionLayoutState !== "ready"
        || current.dataset.initialRouteCertificate === "valid") return;
      markProtocolFailure(
        current,
        "generation-watchdog-timeout",
        "initial-route certificate was not issued for the completed layout generation",
      );
    }, 2500);
  });
  document.addEventListener("change", event => {
    if (event.target?.id === "machine-select") scheduleBind();
  });

  const view = document.getElementById("view") || document.body;
  viewObserver = new MutationObserver(records => {
    if (records.some(record => [...record.addedNodes, ...record.removedNodes].some(node => (
      node?.nodeType === 1 && (
        node.matches?.(".graph-stage,svg.edge-svg")
        || node.querySelector?.(".graph-stage,svg.edge-svg")
      )
    )))) scheduleBind();
  });
  viewObserver.observe(view, {childList: true, subtree: true});

  for (const eventName of ["pagehide", "beforeunload"]) {
    window.addEventListener(eventName, () => {
      destroyed = true;
      settleGeneration += 1;
      clearTimeout(bindTimer);
      routeObserver?.disconnect();
      viewObserver?.disconnect();
    }, {once: true});
  }

  window.glyphInitialTransitionDependencyBridge = Object.freeze({
    marker: MARKER,
    version: 3,
    bind,
    invalidateIfChanged,
    settleCertifiedRoute,
    get signature() { return lastSignature; },
    get settleGeneration() { return settleGeneration; },
  });
  scheduleBind();
})();
</script>
"""


def enhance_initial_transition_dependency_bridge_html(html: str) -> str:
    """Bind initial-route certificates to the completed transition generation."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
