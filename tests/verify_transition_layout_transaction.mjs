import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/transition-layout-transaction");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 180; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph process exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`);
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

async function transactionState(page) {
  return page.evaluate(() => {
    const stage = document.querySelector(".graph-stage");
    return {
      state: stage?.dataset.transitionLayoutState || "missing",
      publication: stage?.dataset.transitionPublicationReady || "missing",
      error: stage?.dataset.transitionLayoutError || "",
      failureCode: stage?.dataset.transitionLayoutFailureCode || "",
      failureDetails: stage?.dataset.transitionLayoutFailureDetails || "",
      generation: Number(stage?.dataset.transitionLayoutGeneration || 0),
      requestedGeneration: Number(window.glyphTransitionLayoutTransaction?.generation || 0),
      completedGeneration: Number(window.glyphTransitionLayoutTransaction?.completedGeneration || 0),
      transactionVersion: Number(window.glyphTransitionLayoutTransaction?.version || 0),
      interactionVersion: Number(window.glyphTransitionLayoutInteractionAdapter?.version || 0),
      viewportVersion: Number(window.glyphDiagramViewport?.version || 0),
      viewportMode: window.glyphDiagramViewport?.mode?.() || "",
      viewportScale: Number(stage?.dataset.viewportScale || 1),
      collision: stage?.dataset.transitionIoCollisionSolved || "",
      collisionCount: Number(stage?.dataset.transitionIoCollisionCount || -1),
      semantic: stage?.dataset.transitionSemanticLinesReady || "",
      roles: stage?.dataset.transitionSemanticRoleLinesReady || "",
      reason: stage?.dataset.transitionLayoutReason || "",
      digest: stage?.dataset.diagramDigest || "",
      audit: window.glyphTransitionLayoutTransaction?.audit?.() || null,
    };
  });
}

async function waitForTransaction(page, minimumGeneration = 0) {
  await page.waitForFunction(minimum => {
    const stage = document.querySelector(".graph-stage");
    const generation = Number(stage?.dataset.transitionLayoutGeneration || 0);
    const state = stage?.dataset.transitionLayoutState;
    const routeState = stage?.dataset.initialRouteReady;
    const certificateState = stage?.dataset.layoutCertificateState;
    const publicationReady = stage?.dataset.transitionPublicationReady;
    const terminalFailure = state === "failed"
      || routeState === "failed"
      || certificateState === "failed";
    return generation >= Number(minimum || 0)
      && (terminalFailure || (state === "ready" && publicationReady === "true"));
  }, minimumGeneration, { timeout: 30000 });
  const result = await transactionState(page);
  assert.equal(result.state, "ready", JSON.stringify(result));
  assert.equal(result.publication, "true", JSON.stringify(result));
  assert.equal(result.collision, "true", JSON.stringify(result));
  assert.equal(result.collisionCount, 0, JSON.stringify(result));
  assert.equal(result.semantic, "true", JSON.stringify(result));
  assert.equal(result.roles, "true", JSON.stringify(result));
  assert.equal(result.transactionVersion, 2, JSON.stringify(result));
  assert.equal(result.interactionVersion, 4, JSON.stringify(result));
  assert.equal(result.viewportVersion, 2, JSON.stringify(result));
  assert.equal(result.audit?.ok, true, JSON.stringify(result.audit));
  assert(result.digest.length > 0, "layout did not publish the source digest");
  return result;
}

async function waitForNextTransaction(page, previousGeneration) {
  await page.waitForFunction(previous => {
    const stage = document.querySelector(".graph-stage");
    const generation = Number(stage?.dataset.transitionLayoutGeneration || 0);
    const state = stage?.dataset.transitionLayoutState;
    return generation > Number(previous || 0) && (state === "ready" || state === "failed");
  }, previousGeneration, { timeout: 30000 });
  return waitForTransaction(page, Number(previousGeneration || 0) + 1);
}

async function waitForViewportFit(page) {
  await page.waitForFunction(() => window.glyphDiagramViewport?.mode?.() === "fit", null, { timeout: 10000 });
  await page.waitForTimeout(120);
  const state = await transactionState(page);
  assert.equal(state.viewportMode, "fit", JSON.stringify(state));
  assert(state.viewportScale > 0 && state.viewportScale <= 1, `unexpected fit scale: ${state.viewportScale}`);
}

async function assertVisibleInViewport(page) {
  const result = await page.evaluate(() => {
    const shell = document.querySelector(".canvas-shell");
    const stage = shell?.querySelector(".graph-stage");
    if (!shell || !stage) return { error: "canvas shell or stage missing" };
    const shellRect = shell.getBoundingClientRect();
    const elements = [
      ...stage.querySelectorAll(".state-node"),
      ...stage.querySelectorAll(".transition-io-cluster"),
    ];
    const outside = elements.map((element, index) => {
      const rect = element.getBoundingClientRect();
      const id = element.dataset.transitionId || element.querySelector(".state-name")?.textContent || String(index);
      const visible = rect.right >= shellRect.left && rect.left <= shellRect.right
        && rect.bottom >= shellRect.top && rect.top <= shellRect.bottom;
      const fullyInside = rect.left >= shellRect.left - 2 && rect.right <= shellRect.right + 2
        && rect.top >= shellRect.top - 2 && rect.bottom <= shellRect.bottom + 2;
      return visible && fullyInside ? null : { id, rect, shellRect };
    }).filter(Boolean);
    return { outside, count: elements.length };
  });
  assert.equal(result.error, undefined, result.error);
  assert(result.count > 0, "no diagram elements were visible");
  assert.deepEqual(result.outside, [], `fit mode left elements outside the viewport: ${JSON.stringify(result.outside)}`);
}

async function placement(locator) {
  return locator.evaluate(element => {
    const left = Number.parseFloat(element.style.left || "0");
    const top = Number.parseFloat(element.style.top || "0");
    const anchorX = Number(element.dataset.anchorX || 0);
    const anchorY = Number(element.dataset.anchorY || 0);
    return {
      left,
      top,
      dx: left - anchorX,
      dy: top - anchorY,
      distance: Math.hypot(left - anchorX, top - anchorY),
      manual: element.dataset.manualIo,
    };
  });
}

async function clickDoesNotPersistManualLayout(page) {
  const cluster = page.locator(".transition-io-cluster").first();
  const transitionId = await cluster.getAttribute("data-transition-id");
  assert(transitionId, "transition id missing before click test");
  const generation = Number(await page.locator(".graph-stage").getAttribute("data-transition-layout-generation") || 0);
  await cluster.click();
  await waitForNextTransaction(page, generation);
  const storedLabel = await page.evaluate(id => {
    const key = Object.keys(localStorage).find(value => value.startsWith("glyph.diagram.transition-io.v1:"));
    return key ? (JSON.parse(localStorage.getItem(key) || "{}")[id] ?? null) : null;
  }, transitionId);
  assert.equal(storedLabel, null, "a simple label click was persisted as a manual drag");
  assert.notEqual(await cluster.getAttribute("data-manual-io"), "true");

  const node = page.locator(".state-node").first();
  const nodeGeneration = Number(await page.locator(".graph-stage").getAttribute("data-transition-layout-generation") || 0);
  await node.click();
  await waitForNextTransaction(page, nodeGeneration);
  const storedNodes = await page.evaluate(() => {
    const key = Object.keys(localStorage).find(value => value.startsWith("glyph.diagram.positions.v1:"));
    return key ? JSON.parse(localStorage.getItem(key) || "{}") : null;
  });
  assert.equal(storedNodes, null, "a simple node click was persisted as a manual drag");
}

async function dragStateNode(page) {
  const node = page.locator(".state-node").first();
  const before = await node.boundingBox();
  assert(before, "state node has no bounding box before drag");
  const generation = Number(await page.locator(".graph-stage").getAttribute("data-transition-layout-generation") || 0);
  const startX = before.x + before.width / 2;
  const startY = before.y + before.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + 170, startY + 160, { steps: 20 });
  await page.mouse.up();
  await waitForNextTransaction(page, generation);
  const after = await node.boundingBox();
  assert(after, "state node has no bounding box after drag");
  assert(Math.abs(after.x - before.x) > 10 || Math.abs(after.y - before.y) > 10, "state node did not move");
  const stored = await page.evaluate(() => Object.keys(localStorage).some(key => key.startsWith("glyph.diagram.positions.v1:")));
  assert(stored, "state node position was not persisted");
}

async function dragFeasibleTransitionCluster(page) {
  const preferred = page.locator('.transition-io-cluster[data-input-value="ConveyorStop"]');
  const all = page.locator(".transition-io-cluster");
  const candidates = [];
  for (let index = 0; index < await preferred.count(); index += 1) candidates.push(preferred.nth(index));
  for (let index = 0; index < await all.count(); index += 1) candidates.push(all.nth(index));
  const deltas = [
    { x: 36, y: 0 }, { x: -36, y: 0 }, { x: 0, y: 36 }, { x: 0, y: -36 },
    { x: 28, y: 28 }, { x: -28, y: 28 }, { x: 28, y: -28 }, { x: -28, y: -28 },
  ];
  const attempted = new Set();
  for (const cluster of candidates) {
    const transitionId = await cluster.getAttribute("data-transition-id");
    if (!transitionId || attempted.has(transitionId)) continue;
    attempted.add(transitionId);
    for (const delta of deltas) {
      const before = await cluster.boundingBox();
      assert(before, `${transitionId}: missing bounding box before drag`);
      const startX = before.x + before.width / 2;
      const startY = before.y + before.height / 2;
      const generation = Number(await page.locator(".graph-stage").getAttribute("data-transition-layout-generation") || 0);
      await page.mouse.move(startX, startY);
      await page.mouse.down();
      await page.mouse.move(startX + delta.x, startY + delta.y, { steps: 20 });
      await page.mouse.up();
      await waitForNextTransaction(page, generation);
      const after = await cluster.boundingBox();
      assert(after, `${transitionId}: missing bounding box after drag`);
      if (Math.abs(after.x - before.x) > 10 || Math.abs(after.y - before.y) > 10) return { cluster, transitionId };
      await cluster.dblclick();
      await waitForNextTransaction(page, Number(await page.locator(".graph-stage").getAttribute("data-transition-layout-generation") || 0) - 1);
    }
  }
  assert.fail("no transition label had a feasible manual drag");
}

async function verifyLongUnbrokenLabel(page) {
  const cluster = page.locator(".transition-io-cluster").first();
  const original = await cluster.evaluate(element => ({
    io: element.dataset.ioValue || "",
    input: element.dataset.inputValue || "",
    guard: element.dataset.guardValue || "",
    output: element.dataset.outputValue || "",
  }));
  const longValue = `VeryLongUnbrokenInput_${"Abc123".repeat(34)}`;
  await cluster.evaluate((element, value) => {
    element.dataset.ioValue = value;
    element.dataset.inputValue = value;
    element.dataset.guardValue = "";
    element.dataset.outputValue = "";
  }, longValue);
  const generation = await page.evaluate(() => window.glyphTransitionLayoutTransaction.run());
  await waitForTransaction(page, generation);
  const result = await cluster.evaluate((element, expected) => {
    const value = element.querySelector(".transition-io-value");
    const lines = [...element.querySelectorAll(".transition-transaction-line")];
    return {
      lineCount: lines.length,
      reconstructed: lines.map(line => line.textContent || "").join(""),
      clipping: value ? {
        horizontal: value.scrollWidth > value.clientWidth + 1.5,
        vertical: value.scrollHeight > value.clientHeight + 1.5,
      } : null,
      expected,
    };
  }, longValue);
  assert(result.lineCount > 1, "long unbroken label was not split into readable lines");
  assert.equal(result.reconstructed, longValue, "long-label wrapping changed semantic text");
  assert.deepEqual(result.clipping, { horizontal: false, vertical: false });
  assert.equal((await transactionState(page)).audit?.ok, true);

  await cluster.evaluate((element, value) => {
    element.dataset.ioValue = value.io;
    element.dataset.inputValue = value.input;
    element.dataset.guardValue = value.guard;
    element.dataset.outputValue = value.output;
  }, original);
  const restoreGeneration = await page.evaluate(() => window.glyphTransitionLayoutTransaction.run());
  await waitForTransaction(page, restoreGeneration);
}

async function verifyResizeAndScheduleConvergence(page) {
  const before = Number(await page.locator(".graph-stage").getAttribute("data-transition-layout-generation") || 0);
  await page.setViewportSize({ width: 1380, height: 900 });
  await waitForNextTransaction(page, before);
  await waitForViewportFit(page);
  await assertVisibleInViewport(page);

  const requested = await page.evaluate(() => {
    window.glyphTransitionLayoutTransaction.schedule("publication-burst-1", 0);
    window.glyphTransitionLayoutTransaction.schedule("publication-burst-2", 0);
    return window.glyphTransitionLayoutTransaction.schedule("publication-burst-3", 0);
  });
  await page.waitForFunction(generation => (
    Number(window.glyphTransitionLayoutTransaction?.completedGeneration || 0) >= generation
    && document.querySelector(".graph-stage")?.dataset.transitionLayoutState === "ready"
  ), requested, { timeout: 30000 });
  const state = await waitForTransaction(page, requested);
  assert(state.completedGeneration >= state.requestedGeneration, JSON.stringify(state));
}

const logs = [];
const browserErrors = [];
const port = 8931;
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
  const page = await browser.newPage({ viewport: { width: 1900, height: 1200 } });
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.stack || error.message}`));
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  if (!await page.locator('button[data-tab="state"]').evaluate(button => button.classList.contains("active"))) await page.click('button[data-tab="state"]');
  await page.selectOption("#machine-select", { label: "Conveyor" });
  await waitForTransaction(page);
  await waitForViewportFit(page);
  await assertVisibleInViewport(page);

  const initialAudit = await page.evaluate(() => window.glyphTransitionLayoutTransaction.audit());
  assert.equal(initialAudit.ok, true, JSON.stringify(initialAudit.violations));
  assert.equal(await page.locator('.transition-io-value:has-text("ConveyorStop")').count() > 0, true);

  await clickDoesNotPersistManualLayout(page);
  await dragStateNode(page);
  const dragged = await dragFeasibleTransitionCluster(page);
  const beforeReload = await placement(dragged.cluster);
  assert.equal(beforeReload.manual, "true");
  assert(beforeReload.distance <= 96.5);

  const storedBefore = await page.evaluate(id => {
    const key = Object.keys(localStorage).find(value => value.startsWith("glyph.diagram.transition-io.v1:"));
    return key ? JSON.parse(localStorage.getItem(key) || "{}")[id] : null;
  }, dragged.transitionId);
  assert(storedBefore, "manual placement was not persisted");
  assert(Math.abs(storedBefore.dx - beforeReload.dx) < 1.5);
  assert(Math.abs(storedBefore.dy - beforeReload.dy) < 1.5);

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  if (!await page.locator('button[data-tab="state"]').evaluate(button => button.classList.contains("active"))) await page.click('button[data-tab="state"]');
  await waitForTransaction(page);
  await waitForViewportFit(page);

  const restored = page.locator(`.transition-io-cluster[data-transition-id="${dragged.transitionId}"]`);
  const afterReload = await placement(restored);
  assert.equal(afterReload.manual, "true");
  assert(afterReload.distance <= 96.5);
  assert(Math.abs(afterReload.dx - beforeReload.dx) < 2, "restored x offset changed");
  assert(Math.abs(afterReload.dy - beforeReload.dy) < 2, "restored y offset changed");

  const storedAfter = await page.evaluate(id => {
    const key = Object.keys(localStorage).find(value => value.startsWith("glyph.diagram.transition-io.v1:"));
    return key ? JSON.parse(localStorage.getItem(key) || "{}")[id] : null;
  }, dragged.transitionId);
  assert(storedAfter, "corrected placement was not written back");
  assert(Math.abs(storedAfter.dx - afterReload.dx) < 1.5);
  assert(Math.abs(storedAfter.dy - afterReload.dy) < 1.5);

  await verifyLongUnbrokenLabel(page);
  await verifyResizeAndScheduleConvergence(page);

  const stableBefore = await page.locator(".graph-stage").getAttribute("data-transition-layout-generation");
  await page.waitForTimeout(900);
  const stableAfter = await page.locator(".graph-stage").getAttribute("data-transition-layout-generation");
  assert.equal(stableAfter, stableBefore, "layout generation kept changing after readiness");
  assert.equal(await page.locator(".graph-stage").getAttribute("data-transition-layout-state"), "ready");
  assert.equal(await page.locator(".graph-stage").getAttribute("data-transition-publication-ready"), "true");

  const finalAudit = await page.evaluate(() => window.glyphTransitionLayoutTransaction.audit());
  assert.equal(finalAudit.ok, true, JSON.stringify(finalAudit.violations));
  assert.deepEqual(browserErrors, [], `unexpected browser errors:\n${browserErrors.join("\n")}`);
  await page.screenshot({ path: path.join(outputDirectory, "conveyor-publication-ready.png"), fullPage: true });
  await page.close();
} catch (error) {
  throw new Error(`${error.stack || error}\n${browserErrors.join("\n")}\n${logs.join("")}`);
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified publication-ready responsive transition layout, persistence, wrapping, and convergence");
