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
  let pending = null;
  let expiryTimer = null;
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
    pending = {
      stage: stageOf(),
      values: semanticSnapshot(),
    };
    expiryTimer = setTimeout(() => {
      pending = null;
    }, 5000);
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

  document.addEventListener("glyph-transition-layout-transaction-ready", install);
  document.addEventListener("glyph-transition-io-clusters-ready", install);
  new MutationObserver(install).observe(
    document.getElementById("view") || document.body,
    {childList: true, subtree: true},
  );
  for (const eventName of ["pagehide", "beforeunload"]) {
    window.addEventListener(eventName, () => {
      destroyed = true;
      pending = null;
      clearTimeout(expiryTimer);
    }, {once: true});
  }

  window.glyphManualLayoutSemanticGuard = {
    marker: MARKER,
    version: 4,
    install,
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
