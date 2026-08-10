import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph process exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`, { cache: "no-store" });
      if (response.ok && (await response.json()).status === "ready") return;
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Glyph server did not become ready\n${logs.join("")}`);
}

async function stopProcess(child) {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    new Promise(resolve => setTimeout(resolve, 1500)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

async function waitStateReady(page, machine) {
  await page.waitForFunction(expected => {
    const selector = document.getElementById("machine-select");
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return selector?.value === expected
      && stage?.dataset.transitionLayoutState === "ready"
      && stage?.dataset.transitionPublicationReady === "true"
      && document.querySelectorAll(".state-node").length > 0;
  }, String(machine), { timeout: 60_000 });
}

const logs = [];
const browserErrors = [];
const port = 8906;
const child = spawn("python3", ["glyph.py", "examples/state_diagrams/dual_machines.glyph"], {
  env: {
    ...process.env,
    GLYPH_DIAGRAM_PORT: String(port),
    GLYPH_DIAGRAM_NO_BROWSER: "1",
    PYTHONUNBUFFERED: "1",
  },
  stdio: ["ignore", "pipe", "pipe"],
});
child.stdout.on("data", chunk => logs.push(chunk.toString()));
child.stderr.on("data", chunk => logs.push(chunk.toString()));

const browser = await chromium.launch({ headless: true });
try {
  const url = `http://127.0.0.1:${port}`;
  await waitForServer(url, child, logs);
  const page = await browser.newPage({ viewport: { width: 1400, height: 880 } });
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready"
    && window.glyphTransitionNodePositionAdapter?.version === 10
    && window.glyphTransitionLayoutInteractionAdapter?.version === 6
    && window.glyphDiagramGuiUxGuard?.version === 4
    && window.glyphDiagramGuiUxContinuity?.version === 5);
  await page.locator('.tab[data-tab="state"]').click();
  await page.waitForFunction(() => document.getElementById("machine-select")?.options.length >= 2);
  await waitStateReady(page, 0);
  await page.evaluate(() => {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith("glyph.diagram.positions.v1:") || key.startsWith("glyph.diagram.transition-io.v1:")) localStorage.removeItem(key);
    }
  });

  const nodeRace = await page.evaluate(() => {
    const selector = document.getElementById("machine-select");
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const node = document.querySelector(".state-node");
    if (!selector || !stage || !node) throw new Error("node race fixture is incomplete");
    const oldNames = [...stage.querySelectorAll(".state-node")].map(item => item.querySelector(".state-name")?.textContent?.trim() || "").filter(Boolean);
    node.classList.add("selected-node");
    node.focus({ preventScroll: true });
    const before = { left: node.style.left, top: node.style.top };
    const width = Number.parseFloat(stage.style.width || "0") || stage.scrollWidth;
    const key = node.offsetLeft + node.offsetWidth + 32 < width ? "ArrowRight" : "ArrowLeft";
    node.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
    const after = { left: node.style.left, top: node.style.top };
    selector.value = "1";
    selector.dispatchEvent(new Event("change", { bubbles: true }));
    return { oldNames, key, moved: before.left !== after.left || before.top !== after.top };
  });
  assert(nodeRace.moved, `node race did not trigger a position change: ${JSON.stringify(nodeRace)}`);
  await waitStateReady(page, 1);
  await page.waitForFunction(() => document.activeElement?.id === "machine-select"
    && window.glyphDiagramGuiUxContinuity?.pendingNodeFocus() === "");
  await page.waitForTimeout(120);
  const nodeStorage = await page.evaluate(() => Object.fromEntries(
    Object.keys(localStorage)
      .filter(key => key.startsWith("glyph.diagram.positions.v1:") && key.endsWith(":state:1"))
      .map(key => [key, JSON.parse(localStorage.getItem(key) || "{}")]),
  ));
  for (const value of Object.values(nodeStorage)) {
    for (const oldName of nodeRace.oldNames) {
      assert(!(oldName in value), `old-machine node ${oldName} leaked into machine 1 storage: ${JSON.stringify(nodeStorage)}`);
    }
  }

  await page.locator("#machine-select").selectOption("0");
  await waitStateReady(page, 0);
  await page.waitForFunction(() => document.activeElement?.id === "machine-select");
  const labelRace = await page.evaluate(() => {
    const selector = document.getElementById("machine-select");
    const cluster = document.querySelector(".transition-io-cluster");
    if (!selector || !cluster) throw new Error("label race fixture is incomplete");
    const transitionId = cluster.dataset.transitionId || "";
    cluster.focus({ preventScroll: true });
    const before = { left: cluster.style.left, top: cluster.style.top };
    cluster.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true }));
    const after = { left: cluster.style.left, top: cluster.style.top };
    selector.value = "1";
    selector.dispatchEvent(new Event("change", { bubbles: true }));
    return { transitionId, moved: before.left !== after.left || before.top !== after.top };
  });
  assert(labelRace.transitionId, "label race has no transition identity");
  assert(labelRace.moved, `label race did not trigger a position change: ${JSON.stringify(labelRace)}`);
  await waitStateReady(page, 1);
  await page.waitForFunction(() => document.activeElement?.id === "machine-select"
    && window.glyphDiagramGuiUxGuard?.pendingClusterFocus() === null);
  await page.waitForTimeout(120);
  const labelStorage = await page.evaluate(() => Object.fromEntries(
    Object.keys(localStorage)
      .filter(key => key.startsWith("glyph.diagram.transition-io.v1:") && key.endsWith(":1"))
      .map(key => [key, JSON.parse(localStorage.getItem(key) || "{}")]),
  ));
  for (const value of Object.values(labelStorage)) {
    assert(!(labelRace.transitionId in value), `old-machine transition ${labelRace.transitionId} leaked into machine 1 storage: ${JSON.stringify(labelStorage)}`);
  }

  await page.locator("#machine-select").selectOption("0");
  await waitStateReady(page, 0);
  const nodeStorageFailure = await page.evaluate(async () => {
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith("glyph.diagram.positions.v1:")) localStorage.removeItem(key);
    }
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const node = document.querySelector(".state-node");
    if (!stage || !node) throw new Error("node storage failure fixture is incomplete");
    const name = node.querySelector(".state-name")?.textContent?.trim() || "";
    node.classList.add("selected-node");
    node.focus({ preventScroll: true });
    const before = { left: node.style.left, top: node.style.top };
    const width = Number.parseFloat(stage.style.width || "0") || stage.scrollWidth;
    const key = node.offsetLeft + node.offsetWidth + 32 < width ? "ArrowRight" : "ArrowLeft";
    const originalSetItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function blockedSetItem(storageKey, value) {
      if (String(storageKey).startsWith("glyph.diagram.positions.v1:")) {
        throw new DOMException("storage blocked by test", "QuotaExceededError");
      }
      return originalSetItem.call(this, storageKey, value);
    };
    try {
      node.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
      const immediate = { left: node.style.left, top: node.style.top };
      await new Promise(resolve => setTimeout(resolve, 80));
      const live = [...document.querySelectorAll(".state-node")].find(item => (item.querySelector(".state-name")?.textContent?.trim() || "") === name);
      return {
        name,
        key,
        before,
        immediate,
        after: live ? { left: live.style.left, top: live.style.top } : null,
        cancelReason: live?.closest(".graph-stage")?.dataset.transitionNodeCancelReason || stage.dataset.transitionNodeCancelReason || "",
        storageKeys: Object.keys(localStorage).filter(storageKey => storageKey.startsWith("glyph.diagram.positions.v1:")),
      };
    } finally {
      Storage.prototype.setItem = originalSetItem;
    }
  });
  assert(nodeStorageFailure.name, "node storage failure has no node identity");
  assert.notDeepEqual(nodeStorageFailure.immediate, nodeStorageFailure.before, "node storage failure did not exercise a move");
  assert.deepEqual(nodeStorageFailure.after, nodeStorageFailure.before, `failed node persistence did not roll back: ${JSON.stringify(nodeStorageFailure)}`);
  assert.equal(nodeStorageFailure.cancelReason, "persistence-unavailable");
  assert.deepEqual(nodeStorageFailure.storageKeys, [], `failed node persistence wrote storage: ${JSON.stringify(nodeStorageFailure)}`);
  await waitStateReady(page, 0);

  const manualLabel = await page.evaluate(async () => {
    const cluster = document.querySelector(".transition-io-cluster");
    if (!cluster) throw new Error("label storage failure fixture is incomplete");
    const id = cluster.dataset.transitionId || "";
    const moved = await window.glyphTransitionLayoutInteractionAdapter.keyboardNudge(cluster, 4, 0);
    return { id, moved };
  });
  assert(manualLabel.id, "manual label fixture has no transition identity");
  assert.equal(manualLabel.moved, true, "manual label setup did not persist");
  await waitStateReady(page, 0);
  const manualStorage = await page.evaluate(id => {
    const entries = Object.fromEntries(
      Object.keys(localStorage)
        .filter(key => key.startsWith("glyph.diagram.transition-io.v1:") && key.endsWith(":0"))
        .map(key => [key, JSON.parse(localStorage.getItem(key) || "{}")]),
    );
    return { entries, containsId: Object.values(entries).some(value => id in value) };
  }, manualLabel.id);
  assert.equal(manualStorage.containsId, true, `manual label setup was not stored: ${JSON.stringify(manualStorage)}`);

  const labelResetFailure = await page.evaluate(async id => {
    const cluster = [...document.querySelectorAll(".transition-io-cluster")].find(item => item.dataset.transitionId === id);
    if (!cluster) throw new Error("manual label disappeared before reset failure test");
    cluster.focus({ preventScroll: true });
    const originalSetItem = Storage.prototype.setItem;
    Storage.prototype.setItem = function blockedSetItem(storageKey, value) {
      if (String(storageKey).startsWith("glyph.diagram.transition-io.v1:")) {
        throw new DOMException("storage blocked by test", "QuotaExceededError");
      }
      return originalSetItem.call(this, storageKey, value);
    };
    try {
      cluster.dispatchEvent(new KeyboardEvent("keydown", { key: "Delete", bubbles: true, cancelable: true }));
      await new Promise(resolve => setTimeout(resolve, 80));
      const live = [...document.querySelectorAll(".transition-io-cluster")].find(item => item.dataset.transitionId === id) || cluster;
      return {
        manualIo: live.dataset.manualIo || "",
        gestureState: live.dataset.manualIoGestureState || "",
        gestureReason: live.dataset.manualIoGestureReason || "",
        stored: Object.keys(localStorage)
          .filter(key => key.startsWith("glyph.diagram.transition-io.v1:") && key.endsWith(":0"))
          .some(key => id in JSON.parse(localStorage.getItem(key) || "{}")),
      };
    } finally {
      Storage.prototype.setItem = originalSetItem;
    }
  }, manualLabel.id);
  assert.equal(labelResetFailure.manualIo, "true", `failed label reset changed visible ownership: ${JSON.stringify(labelResetFailure)}`);
  assert.equal(labelResetFailure.gestureState, "reset-failed");
  assert.equal(labelResetFailure.gestureReason, "persistence-unavailable");
  assert.equal(labelResetFailure.stored, true, `failed label reset deleted persisted placement: ${JSON.stringify(labelResetFailure)}`);

  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify({
    nodeRaceKey: nodeRace.key,
    nodeMoved: nodeRace.moved,
    nodeStorageKeys: Object.keys(nodeStorage),
    selectorFocusRestored: true,
    labelTransitionId: labelRace.transitionId,
    labelMoved: labelRace.moved,
    labelStorageKeys: Object.keys(labelStorage),
    staleTransitionFocusBlocked: true,
    nodeStorageFailureRolledBack: true,
    labelResetFailurePreservedManualPlacement: true,
  }));
} finally {
  await browser.close();
  await stopProcess(child);
}
