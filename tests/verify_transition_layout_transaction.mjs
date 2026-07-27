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
      error: stage?.dataset.transitionLayoutError || "",
      generation: Number(stage?.dataset.transitionLayoutGeneration || 0),
      collision: stage?.dataset.transitionIoCollisionSolved || "",
      collisionCount: Number(stage?.dataset.transitionIoCollisionCount || -1),
      semantic: stage?.dataset.transitionSemanticLinesReady || "",
      roles: stage?.dataset.transitionSemanticRoleLinesReady || "",
      reason: stage?.dataset.transitionLayoutReason || "",
      audit: window.glyphTransitionLayoutTransaction?.audit?.() || null,
    };
  });
}

async function waitForTransaction(page) {
  await page.waitForFunction(() => {
    const state = document.querySelector(".graph-stage")?.dataset.transitionLayoutState;
    return state === "ready" || state === "failed";
  }, null, { timeout: 15000 });
  const result = await transactionState(page);
  assert.equal(result.state, "ready", JSON.stringify(result));
  assert.equal(result.collision, "true", JSON.stringify(result));
  assert.equal(result.collisionCount, 0, JSON.stringify(result));
  assert.equal(result.semantic, "true", JSON.stringify(result));
  assert.equal(result.roles, "true", JSON.stringify(result));
}

async function waitForNextTransaction(page, previousGeneration) {
  await page.waitForFunction(previous => {
    const stage = document.querySelector(".graph-stage");
    const generation = Number(stage?.dataset.transitionLayoutGeneration || 0);
    const state = stage?.dataset.transitionLayoutState;
    return generation > Number(previous || 0) && (state === "ready" || state === "failed");
  }, previousGeneration, { timeout: 10000 });
  await waitForTransaction(page);
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

async function dragStateNode(page) {
  const node = page.locator(".state-node").first();
  const before = await node.boundingBox();
  assert(before, "state node has no bounding box before drag");
  const generation = await page.locator(".graph-stage").getAttribute("data-transition-layout-generation");
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
      const generation = await page.locator(".graph-stage").getAttribute("data-transition-layout-generation");
      await page.mouse.move(startX, startY);
      await page.mouse.down();
      await page.mouse.move(startX + delta.x, startY + delta.y, { steps: 20 });
      await page.mouse.up();
      await waitForNextTransaction(page, generation);
      const after = await cluster.boundingBox();
      assert(after, `${transitionId}: missing bounding box after drag`);
      if (Math.abs(after.x - before.x) > 10 || Math.abs(after.y - before.y) > 10) return { cluster, transitionId };
      await cluster.dblclick();
      await page.evaluate(() => window.glyphTransitionLayoutTransaction.run());
      await waitForTransaction(page);
    }
  }
  assert.fail("no transition label had a feasible manual drag");
}

const logs = [];
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
    if (message.type() === "error") logs.push(`browser error: ${message.text()}\n`);
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  if (!await page.locator('button[data-tab="state"]').evaluate(button => button.classList.contains("active"))) await page.click('button[data-tab="state"]');
  await page.selectOption("#machine-select", { label: "Conveyor" });
  await waitForTransaction(page);

  const initialAudit = await page.evaluate(() => window.glyphTransitionLayoutTransaction.audit());
  assert.equal(initialAudit.ok, true, JSON.stringify(initialAudit.violations));
  assert.equal(await page.locator('.transition-io-value:has-text("ConveyorStop")').count() > 0, true);

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

  const stableBefore = await page.locator(".graph-stage").getAttribute("data-transition-layout-generation");
  await page.waitForTimeout(900);
  const stableAfter = await page.locator(".graph-stage").getAttribute("data-transition-layout-generation");
  assert.equal(stableAfter, stableBefore, "layout generation kept changing after readiness");
  assert.equal(await page.locator(".graph-stage").getAttribute("data-transition-layout-state"), "ready");

  const finalAudit = await page.evaluate(() => window.glyphTransitionLayoutTransaction.audit());
  assert.equal(finalAudit.ok, true, JSON.stringify(finalAudit.violations));
  await page.screenshot({ path: path.join(outputDirectory, "conveyor-restored.png"), fullPage: true });
  await page.close();
} catch (error) {
  throw new Error(`${error.stack || error}\n${logs.join("")}`);
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified deterministic node and transition layout transaction across reload");
