from __future__ import annotations


_MARKER = "glyph-manual-layout-semantic-guard-v1"


_SCRIPT = r"""
<script id="glyph-manual-layout-semantic-guard-v1-script">
(() => {
  const MARKER = "glyph-manual-layout-semantic-guard-v1";
  const SEMANTIC_KEYS = [
    "ioValue",
    "inputValue",
    "guardValue",
    "actionValue",
    "outputValue",
    "emittedOutputValue",
  ];
  const ROUTE_WAIT_LIMIT = 400;
  const ROUTE_WAIT_DELAY_MS = 25;
  let pending = null;
  let expiryTimer = null;
  let publicationWaitToken = 0;
  let destroyed = false;

  function stageOf() {
    return document.querySelector(".state-node")?.closest(".graph-stage") || null;
  }

  function semanticSnapshot() {
    const values = new Map();
    document.querySelectorAll(".transition-io-cluster").forEach((cluster, index) => {
      const id = cluster.dataset.transitionId || `index:${index}`;
      const semantic = {};
      for (const key of SEMANTIC_KEYS) {
        semantic[key] = Object.prototype.hasOwnProperty.call(cluster.dataset, key)
          ? cluster.dataset[key]
          : null;
      }
      values.set(id, semantic);
    });
    return values;
  }

  function restoreSemanticSnapshot(values) {
    let restored = 0;
    document.querySelectorAll(".transition-io-cluster").forEach((cluster, index) => {
      const id = cluster.dataset.transitionId || `index:${index}`;
      const semantic = values.get(id);
      if (!semantic) return;
      for (const key of SEMANTIC_KEYS) {
        const value = semantic[key];
        if (value === null) delete cluster.dataset[key];
        else cluster.dataset[key] = value;
      }
      restored += 1;
    });
    return restored;
  }

  function armManualRun() {
    clearTimeout(expiryTimer);
    publicationWaitToken += 1;
    pending = {
      stage: stageOf(),
      values: semanticSnapshot(),
    };
    expiryTimer = setTimeout(() => {
      pending = null;
    }, 5000);
  }

  function waitForRouteAndPublish(stage, router, generation, token, attempt = 0) {
    if (destroyed || token !== publicationWaitToken || !stage?.isConnected) return;
    const routeComplete = Number(router.completedGeneration || 0) >= generation;
    if (routeComplete) {
      if (stage.dataset.initialRouteReady === "failed"
        || stage.dataset.initialRouteCertificate === "failed") {
        stage.dataset.manualLayoutSemanticGuard = "route-certification-failed";
        return;
      }
      const certificate = window.glyphLayoutPublicationCertificate;
      if (stage.dataset.initialRouteReady === "true"
        && stage.dataset.initialRouteCertificate === "valid"
        && certificate
        && typeof certificate.schedule === "function") {
        stage.dataset.manualLayoutSemanticGuard = "publication-certification-requested";
        certificate.schedule("manual-layout-semantics-restored", 0);
        return;
      }
    }
    if (attempt >= ROUTE_WAIT_LIMIT) {
      stage.dataset.manualLayoutSemanticGuard = "publication-wait-timeout";
      console.error("manual layout publication recertification timed out", {
        marker: MARKER,
        generation,
        completedGeneration: router.completedGeneration,
        initialRouteReady: stage.dataset.initialRouteReady,
        initialRouteCertificate: stage.dataset.initialRouteCertificate,
      });
      return;
    }
    setTimeout(() => waitForRouteAndPublish(
      stage,
      router,
      generation,
      token,
      attempt + 1,
    ), ROUTE_WAIT_DELAY_MS);
  }

  function requestPublicationRecertification() {
    const stage = stageOf();
    const restoration = stage?.dataset.manualLayoutSemanticGuard || "";
    if (!stage
      || stage.dataset.transitionLayoutReason !== "manual-run"
      || stage.dataset.transitionLayoutState !== "ready"
      || stage.dataset.transitionPublicationReady === "true"
      || !restoration.startsWith("restored:")) return false;
    const router = window.glyphInitialTransitionRouter;
    if (!router || typeof router.schedule !== "function") return false;
    const token = ++publicationWaitToken;
    stage.dataset.manualLayoutSemanticGuard = `route-certification-requested:${restoration}`;
    stage.dataset.initialRouteReady = "pending";
    const generation = router.schedule("manual-layout-semantics-restored", 0);
    waitForRouteAndPublish(stage, router, generation, token);
    return true;
  }

  function install() {
    const transaction = window.glyphTransitionLayoutTransaction;
    const renderer = window.glyphTransitionIoClusters;
    if (!transaction || !renderer || typeof renderer.render !== "function") return false;

    if (transaction.manualSemanticGuard !== MARKER) {
      const originalRun = transaction.run.bind(transaction);
      transaction.run = () => {
        armManualRun();
        return originalRun();
      };
      transaction.manualSemanticGuard = MARKER;
    }

    if (renderer.manualSemanticGuard !== MARKER) {
      const originalRender = renderer.render.bind(renderer);
      renderer.render = async (...args) => {
        const candidate = pending;
        const result = await originalRender(...args);
        const stage = stageOf();
        const manualTransaction = Boolean(
          candidate
          && pending === candidate
          && candidate.stage === stage
          && stage?.dataset.transitionLayoutState === "pending"
          && stage?.dataset.transitionLayoutReason === "manual-run"
        );
        if (manualTransaction) {
          const restored = restoreSemanticSnapshot(candidate.values);
          pending = null;
          clearTimeout(expiryTimer);
          stage.dataset.manualLayoutSemanticGuard = `restored:${restored}`;
          document.dispatchEvent(new CustomEvent(
            "glyph-manual-layout-semantics-restored",
            {detail: {marker: MARKER, restored}},
          ));
        }
        return result;
      };
      renderer.manualSemanticGuard = MARKER;
    }
    return true;
  }

  document.addEventListener("glyph-transition-layout-transaction-ready", () => {
    install();
    requestPublicationRecertification();
  });
  document.addEventListener("glyph-transition-io-clusters-ready", install);
  new MutationObserver(install).observe(
    document.getElementById("view") || document.body,
    {childList: true, subtree: true},
  );
  for (const eventName of ["pagehide", "beforeunload"]) {
    window.addEventListener(eventName, () => {
      destroyed = true;
      pending = null;
      publicationWaitToken += 1;
      clearTimeout(expiryTimer);
    }, {once: true});
  }

  window.glyphManualLayoutSemanticGuard = {
    marker: MARKER,
    version: 2,
    install,
    requestPublicationRecertification,
    get armed() { return Boolean(pending) && !destroyed; },
  };
  install();
})();
</script>
"""


def enhance_manual_layout_semantic_guard_html(html: str) -> str:
    """Keep current semantic label data intact during manual layout-only runs."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
