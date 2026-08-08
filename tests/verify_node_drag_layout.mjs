import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
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

async function state(page) {
  return page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const transaction = window.glyphTransitionLayoutTransaction;
    const clusters = [...(stage?.querySelectorAll(".transition-io-cluster") || [])];
    const workspace = window.glyphStateDiagramWorkspace;
    return {
      layoutState: stage?.dataset.transitionLayoutState || "",
      layoutReason: stage?.dataset.transitionLayoutReason || "",
      layoutError: stage?.dataset.transitionLayoutError || "",
      publicationReady: stage?.dataset.transitionPublicationReady || "",
      layoutProfile: stage?.dataset.transitionLayoutProfile || "",
      layoutMode: stage?.dataset.transitionLayoutMode || "",
      denseCanvas: stage?.dataset.transitionDenseCanvas || "",
      transactionGeneration: transaction?.generation ?? null,
      transactionCompletedGeneration: transaction?.completedGeneration ?? null,
      nodeAdapterVersion: window.glyphTransitionNodePositionAdapter?.version ?? null,
      nodeGuardVersion: window.glyphTransitionNodeLayoutGuard?.version ?? null,
      workspaceVersion: workspace?.version ?? null,
      workspaceAudit: workspace?.audit?.() ?? null,
      workspaceWidth: Number.parseFloat(stage?.style.width || "0") || 0,
      workspaceHeight: Number.parseFloat(stage?.style.height || "0") || 0,
      workspaceOriginReady: stage?.dataset.stateDiagramWorkspaceOriginReady || "",
      workspaceGeometryReady: stage?.dataset.stateDiagramWorkspaceGeometryReady || "",
      initialRouteReady: stage?.dataset.initialRouteReady || "",
      initialRouteCertificate: stage?.dataset.initialRouteCertificate || "",
      transitionDetails: document.querySelectorAll(".transition-index .transition-detail").length,
      persisted: Object.keys(localStorage).some(key => key.startsWith("glyph.diagram.positions.v1:")),
      maximumLabelDistance: Math.max(0, ...clusters.map(cluster => Number(cluster.dataset.ioDistance || 0))),
      labelDistanceLimit: Number(stage?.dataset.transitionIoMaxDistance || 0),
      certificatePresent: Boolean(window.glyphLayoutPublicationCertificate),
      routerPresent: Boolean(window.glyphInitialTransitionRouter),
    };
  });
}

async function nodePositions(page) {
  return page.evaluate(() => [...document.querySelectorAll(".state-node")].map(node => ({
    name: node.querySelector(".state-name,.node-name")?.textContent?.trim() || "",
    left: Number.parseFloat(node.style.left || "0") || 0,
    top: Number.parseFloat(node.style.top || "0") || 0,
    selected: node.classList.contains("selected-node"),
    initial: node.classList.contains("initial-target"),
  })));
}

async function waitForPersistedPositions(page, label) {
  await page.waitForFunction(() => {
    const digest = snapshot?.digest || "source";
    const machine = document.getElementById("machine-select")?.value || 0;
    const key = `glyph.diagram.positions.v1:${digest}:state:${machine}`;
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem(key) || "null"); } catch { return false; }
    if (!saved || typeof saved !== "object") return false;
    const nodes = [...document.querySelectorAll(".state-node")];
    if (!nodes.length) return false;
    return nodes.every(node => {
      const name = node.querySelector(".state-name,.node-name")?.textContent?.trim() || "";
      const position = saved[name];
      if (!position) return false;
      const left = Number.parseFloat(node.style.left || "0") || 0;
      const top = Number.parseFloat(node.style.top || "0") || 0;
      return Math.abs(Number(position.x) - left) <= 0.5
        && Math.abs(Number(position.y) - top) <= 0.5;
    });
  }, null, { timeout: 4000 });
  const current = await state(page);
  assert.equal(current.persisted, true, `${label} did not produce a persisted node-position snapshot`);
}

async function initialGeometry(page) {
  return page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const node = stage?.querySelector(".state-node.initial-target");
    const path = stage?.querySelector(":scope > svg.edge-svg > path.initial-transition-path");
    const dot = stage?.querySelector(".initial-dot");
    return {
      name: node?.querySelector(".state-name")?.textContent?.trim() || "",
      nodeLeft: Number.parseFloat(node?.style.left || "0") || 0,
      nodeTop: Number.parseFloat(node?.style.top || "0") || 0,
      path: path?.getAttribute("d") || "",
      dotLeft: Number.parseFloat(dot?.style.left || "0") || 0,
      dotTop: Number.parseFloat(dot?.style.top || "0") || 0,
      side: path?.dataset.routeSide || "",
    };
  });
}

async function drag(page, locator, deltaX, deltaY) {
  const box = await locator.boundingBox();
  assert(box, "state node has no bounding box");
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + deltaX, y + deltaY, { steps: 12 });
  await page.mouse.up();
}

function ready(current, minimumGeneration = 0, requirePersisted = false) {
  return current.layoutState === "ready"
    && current.publicationReady === "true"
    && current.layoutProfile === "ordinary"
    && current.layoutMode === "base"
    && current.denseCanvas === "disabled"
    && current.layoutError === ""
    && Number(current.transactionGeneration || 0) >= minimumGeneration
    && current.transactionGeneration === current.transactionCompletedGeneration
    && (!requirePersisted || current.persisted)
    && current.maximumLabelDistance <= current.labelDistanceLimit + 0.5
    && current.workspaceVersion === 4
    && current.workspaceAudit?.ok === true
    && current.workspaceAudit?.dragActive === false
    && Number(current.workspaceAudit?.dragBudgetMs || 0) === 8
    && current.workspaceWidth >= 1600
    && current.workspaceHeight >= 960
    && current.workspaceOriginReady === "true"
    && current.workspaceGeometryReady === "true"
    && current.initialRouteReady === "true"
    && current.initialRouteCertificate === "ordinary-obstacle-free"
    && current.transitionDetails > 0;
}

async function waitForReady(page, label, minimumGeneration = 0, requirePersisted = false) {
  const samples = [];
  for (let attempt = 0; attempt < 80; attempt += 1) {
    const current = await state(page);
    if (!samples.length || JSON.stringify(current) !== JSON.stringify(samples.at(-1))) samples.push(current);
    if (ready(current, minimumGeneration, requirePersisted)) return current;
    await page.waitForTimeout(50);
  }
  throw new Error(`${label} did not converge: ${JSON.stringify(samples.at(-1))}`);
}

async function waitForQuiescence(page, label, minimumGeneration) {
  let previous = "";
  let stableSamples = 0;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const currentState = await state(page);
    const positions = await nodePositions(page);
    const initial = await initialGeometry(page);
    const signature = JSON.stringify({ currentState, positions, initial });
    if (ready(currentState, minimumGeneration, true) && signature === previous) {
      stableSamples += 1;
      if (stableSamples >= 3) return { currentState, positions, initial };
    } else {
      stableSamples = 0;
    }
    previous = signature;
    await page.waitForTimeout(50);
  }
  throw new Error(`${label} did not remain quiescent: ${previous}`);
}

const logs = [];
const browserErrors = [];
const port = 8898;
const child = spawn("python3", ["glyph.py", "examples/state_diagrams/conveyor_control.glyph"], {
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
  const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  const initial = await waitForReady(page, "initial");

  assert.equal(initial.nodeAdapterVersion, 8, JSON.stringify(initial));
  assert.equal(initial.nodeGuardVersion, 2, JSON.stringify(initial));
  assert.equal(initial.workspaceVersion, 4, JSON.stringify(initial));
  assert.equal(initial.workspaceAudit?.dragBudgetMs, 8, JSON.stringify(initial));
  assert.equal(initial.certificatePresent, false, JSON.stringify(initial));
  assert.equal(initial.routerPresent, false, JSON.stringify(initial));
  assert(initial.transitionDetails > 0, JSON.stringify(initial));

  const initialBefore = await initialGeometry(page);
  assert(initialBefore.name, "initial target was not identified");
  assert(initialBefore.path, "initial transition path is missing");
  const initialNode = page.locator(".state-node.initial-target");
  assert.equal(await initialNode.count(), 1, "initial target node is not unique");
  await drag(page, initialNode, 120, 90);
  await page.waitForFunction(before => {
    const node = document.querySelector(".state-node.initial-target");
    const path = document.querySelector("path.initial-transition-path");
    const dot = document.querySelector(".initial-dot");
    if (!node || !path || !dot) return false;
    const left = Number.parseFloat(node.style.left || "0") || 0;
    const top = Number.parseFloat(node.style.top || "0") || 0;
    const dotLeft = Number.parseFloat(dot.style.left || "0") || 0;
    const dotTop = Number.parseFloat(dot.style.top || "0") || 0;
    return (Math.abs(left - before.nodeLeft) > 1 || Math.abs(top - before.nodeTop) > 1)
      && path.getAttribute("d") !== before.path
      && (Math.abs(dotLeft - before.dotLeft) > 1 || Math.abs(dotTop - before.dotTop) > 1);
  }, initialBefore, { timeout: 3000 });
  await waitForPersistedPositions(page, "pointer drag");
  const pointerReady = await waitForReady(
    page,
    "initial-node-pointer",
    Number(initial.transactionGeneration || 0) + 1,
    true,
  );
  const initialAfter = await initialGeometry(page);
  assert.equal(initialAfter.name, initialBefore.name);
  assert.notEqual(initialAfter.path, initialBefore.path, "initial arrow did not follow the moved node");
  assert(
    Math.abs(initialAfter.dotLeft - initialBefore.dotLeft) > 1
      || Math.abs(initialAfter.dotTop - initialBefore.dotTop) > 1,
    "initial dot did not follow the moved node",
  );

  const detail = page.locator(".transition-index .transition-detail").first();
  assert.equal(await detail.count(), 1, "transition detail row is missing");
  await detail.click();
  assert.equal(await detail.evaluate(element => element.classList.contains("transition-focus")), true);
  assert.equal(await page.locator("path.state-transition-path.transition-focus").count(), 1);

  const keyboardSetup = await page.evaluate(() => {
    const node = document.querySelector(".state-node.selected-node") || document.querySelector(".state-node");
    const stage = node?.closest(".graph-stage");
    if (!node || !stage) return null;
    node.classList.add("selected-node");
    const left = Number.parseFloat(node.style.left || "0") || 0;
    const top = Number.parseFloat(node.style.top || "0") || 0;
    const width = Number.parseFloat(stage.style.width || "0") || stage.scrollWidth;
    const direction = left + node.offsetWidth + 24 < width ? "ArrowRight" : "ArrowLeft";
    document.activeElement?.blur?.();
    return { left, top, direction };
  });
  assert(keyboardSetup, "keyboard drag setup failed");
  const keyboardGeneration = Number(pointerReady.transactionGeneration || 0) + 1;
  await page.keyboard.press(keyboardSetup.direction);
  const keyboardPositions = await nodePositions(page);
  const selected = keyboardPositions.find(item => item.selected);
  assert(selected, "selected node disappeared after keyboard movement");
  assert(
    Math.abs(selected.left - keyboardSetup.left) > 1 || Math.abs(selected.top - keyboardSetup.top) > 1,
    "keyboard movement did not change node position",
  );
  await waitForPersistedPositions(page, "keyboard movement");
  const keyboardReady = await waitForReady(page, "keyboard-node", keyboardGeneration, true);

  const firstQuiescent = await waitForQuiescence(
    page,
    "post-drag",
    Number(keyboardReady.transactionGeneration || 0),
  );
  await waitForPersistedPositions(page, "pre-reload quiescence");
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  const reloaded = await waitForReady(page, "reload", 0, true);
  const secondQuiescent = await waitForQuiescence(
    page,
    "reload-quiescence",
    Number(reloaded.transactionGeneration || 0),
  );

  const positionsByName = items => new Map(items.map(item => [item.name, item]));
  const firstPositions = positionsByName(firstQuiescent.positions);
  const secondPositions = positionsByName(secondQuiescent.positions);
  for (const [name, before] of firstPositions) {
    const after = secondPositions.get(name);
    assert(after, `state node ${name} disappeared after reload`);
    assert(Math.abs(after.left - before.left) <= 1, `${name} left position changed after reload`);
    assert(Math.abs(after.top - before.top) <= 1, `${name} top position changed after reload`);
  }
  assert.equal(secondQuiescent.currentState.initialRouteCertificate, "ordinary-obstacle-free");
  assert.equal(secondQuiescent.currentState.workspaceAudit?.initialCollisions, 0);
  assert(secondQuiescent.currentState.maximumLabelDistance <= secondQuiescent.currentState.labelDistanceLimit + 0.5);
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));

  console.log(JSON.stringify({
    initialGeneration: initial.transactionGeneration,
    pointerGeneration: pointerReady.transactionGeneration,
    keyboardGeneration: keyboardReady.transactionGeneration,
    workspaceVersion: secondQuiescent.currentState.workspaceVersion,
    fullGeometryPasses: secondQuiescent.currentState.workspaceAudit?.fullGeometryPasses,
    incidentGeometryPasses: secondQuiescent.currentState.workspaceAudit?.incidentGeometryPasses,
    initialRouteCertificate: secondQuiescent.currentState.initialRouteCertificate,
    persisted: secondQuiescent.currentState.persisted,
  }));
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}
