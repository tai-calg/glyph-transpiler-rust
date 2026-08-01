import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/transition-layout-transaction");
await fs.mkdir(outputDirectory, { recursive: true });
const file = "examples/acceptance/door_controller.glyph";
const port = 8877;
const url = `http://127.0.0.1:${port}`;
const logs = [];

async function waitForServer(child) {
  for (let attempt = 0; attempt < 180; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph process exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`, { cache: "no-store" });
      if (response.ok && (await response.json()).status === "ready") return;
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Glyph server did not become ready\n${logs.join("")}`);
}

async function stop(child) {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    new Promise(resolve => setTimeout(resolve, 1500)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

async function waitForOrdinaryLayout(page, minimumGeneration = 0) {
  await page.waitForFunction(minimum => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const transaction = window.glyphTransitionLayoutTransaction;
    return Number(stage?.dataset.transitionLayoutGeneration || 0) >= Number(minimum || 0)
      && stage?.dataset.transitionLayoutState === "ready"
      && stage?.dataset.transitionPublicationReady === "true"
      && stage?.dataset.transitionIoClustersReady === "true"
      && stage?.dataset.transitionEnablingCasesReady === "true"
      && stage?.dataset.transitionLayoutProfile === "ordinary"
      && transaction?.generation === transaction?.completedGeneration;
  }, minimumGeneration, { timeout: 5000 });
}

async function layoutState(page) {
  return page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const clusters = [...(stage?.querySelectorAll(".transition-io-cluster") || [])];
    const transaction = window.glyphTransitionLayoutTransaction;
    const workspace = window.glyphStateDiagramWorkspace;
    return {
      layoutState: stage?.dataset.transitionLayoutState || "",
      publicationReady: stage?.dataset.transitionPublicationReady || "",
      layoutProfile: stage?.dataset.transitionLayoutProfile || "",
      layoutMode: stage?.dataset.transitionLayoutMode || "",
      layoutBudgetMs: Number(stage?.dataset.transitionLayoutBudgetMs || 0),
      renderBudgetMs: Number(stage?.dataset.transitionIoRenderBudgetMs || 0),
      renderDurationMs: Number(stage?.dataset.transitionIoRenderDurationMs || 0),
      denseCanvas: stage?.dataset.transitionDenseCanvas || "",
      generation: Number(stage?.dataset.transitionLayoutGeneration || 0),
      error: stage?.dataset.transitionLayoutError || "",
      transitionCount: clusters.length,
      maximumLabelDistance: Math.max(0, ...clusters.map(cluster => Number(cluster.dataset.ioDistance || 0))),
      labelDistanceLimit: Number(stage?.dataset.transitionIoMaxDistance || 0),
      transactionVersion: transaction?.version ?? null,
      transactionGeneration: transaction?.generation ?? null,
      completedGeneration: transaction?.completedGeneration ?? null,
      workspaceVersion: workspace?.version ?? null,
      workspaceAudit: workspace?.audit?.() ?? null,
      detailCount: document.querySelectorAll(".transition-index .transition-detail").length,
      initialReady: stage?.dataset.initialRouteReady || "",
      initialCertificate: stage?.dataset.initialRouteCertificate || "",
      hasCertificate: Boolean(window.glyphLayoutPublicationCertificate),
      hasLegacyRouter: Boolean(window.glyphInitialTransitionRouter),
    };
  });
}

async function elementPosition(locator) {
  return locator.evaluate(element => ({
    left: Number.parseFloat(element.style.left || "0") || 0,
    top: Number.parseFloat(element.style.top || "0") || 0,
  }));
}

async function pointerDrag(page, locator, dx, dy, steps = 8) {
  const box = await locator.boundingBox();
  if (!box) return false;
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y + dy, { steps });
  await page.mouse.up();
  return true;
}

async function dragOneNode(page) {
  const nodes = page.locator(".state-node");
  const deltas = [[120, 0], [-120, 0], [0, 120], [0, -120], [96, 96], [-96, 96]];
  for (let index = 0; index < await nodes.count(); index += 1) {
    const node = nodes.nth(index);
    for (const [dx, dy] of deltas) {
      const before = await elementPosition(node);
      if (!(await pointerDrag(page, node, dx, dy))) continue;
      await page.waitForTimeout(100);
      const after = await elementPosition(node);
      if (Math.abs(after.left - before.left) <= 4 && Math.abs(after.top - before.top) <= 4) continue;
      await page.waitForFunction(() => {
        const stage = document.querySelector(".state-node")?.closest(".graph-stage");
        return stage?.dataset.transitionNodePositions?.startsWith("saved:") === true;
      }, null, { timeout: 3000 });
      return { before, after };
    }
  }
  assert.fail("no state node could be edited");
}

async function labelGestureState(cluster) {
  return cluster.evaluate(element => ({
    left: Number.parseFloat(element.style.left || "0") || 0,
    top: Number.parseFloat(element.style.top || "0") || 0,
    state: element.dataset.manualIoGestureState || "",
    reason: element.dataset.manualIoGestureReason || "",
  }));
}

async function dragOneLabel(page) {
  const clusters = page.locator(".transition-io-cluster");
  const deltas = [[24, 0], [-24, 0], [0, 24], [0, -24], [18, 18], [-18, 18]];
  const attempts = [];
  for (let index = 0; index < await clusters.count(); index += 1) {
    const cluster = clusters.nth(index);
    for (const [dx, dy] of deltas) {
      const before = await labelGestureState(cluster);
      if (!(await pointerDrag(page, cluster, dx, dy, 6))) continue;
      let terminal = null;
      for (let poll = 0; poll < 30; poll += 1) {
        await page.waitForTimeout(50);
        const current = await labelGestureState(cluster);
        if (["persisted", "rejected", "cancelled", "failed", "disconnected"].includes(current.state)) {
          terminal = current;
          break;
        }
      }
      attempts.push({ index, dx, dy, before, terminal });
      if (terminal?.state === "persisted"
        && (Math.abs(terminal.left - before.left) > 2 || Math.abs(terminal.top - before.top) > 2)) {
        return terminal;
      }
    }
  }
  assert.fail(`no transition label could be persisted: ${JSON.stringify(attempts)}`);
}

const child = spawn("python3", ["glyph.py", file], {
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
  await waitForServer(child);
  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  const consoleErrors = [];
  page.on("console", message => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  const started = Date.now();
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await waitForOrdinaryLayout(page);
  const initialLatencyMs = Date.now() - started;
  const initial = await layoutState(page);

  assert(initialLatencyMs < 5000, `initial state rendering took ${initialLatencyMs}ms`);
  assert.equal(initial.layoutState, "ready", JSON.stringify(initial));
  assert.equal(initial.publicationReady, "true", JSON.stringify(initial));
  assert.equal(initial.layoutProfile, "ordinary", JSON.stringify(initial));
  assert.equal(initial.layoutMode, "base", JSON.stringify(initial));
  assert.equal(initial.layoutBudgetMs, 48, JSON.stringify(initial));
  assert.equal(initial.renderBudgetMs, 16, JSON.stringify(initial));
  assert.equal(initial.denseCanvas, "disabled", JSON.stringify(initial));
  assert.equal(initial.error, "", JSON.stringify(initial));
  assert(initial.transitionCount > 0, "no transition labels rendered");
  assert(initial.maximumLabelDistance <= initial.labelDistanceLimit + 0.5, JSON.stringify(initial));
  assert.equal(initial.transactionVersion, 8, JSON.stringify(initial));
  assert.equal(initial.transactionGeneration, initial.completedGeneration, JSON.stringify(initial));
  assert.equal(initial.workspaceVersion, 2, JSON.stringify(initial));
  assert.equal(initial.workspaceAudit?.ok, true, JSON.stringify(initial));
  assert(initial.detailCount > 0, JSON.stringify(initial));
  assert.equal(initial.initialReady, "true", JSON.stringify(initial));
  assert.equal(initial.initialCertificate, "ordinary-follow", JSON.stringify(initial));
  assert.equal(initial.hasCertificate, false, JSON.stringify(initial));
  assert.equal(initial.hasLegacyRouter, false, JSON.stringify(initial));

  let generation = initial.generation;
  const returnLatencies = [];
  for (let cycle = 0; cycle < 8; cycle += 1) {
    await page.click('button[data-tab="io"]');
    await page.waitForFunction(() => document.querySelector(".tab.active")?.dataset.tab === "io");
    const returnedAt = Date.now();
    await page.click('button[data-tab="state"]');
    await waitForOrdinaryLayout(page, generation + 1);
    returnLatencies.push(Date.now() - returnedAt);
    const current = await layoutState(page);
    generation = current.generation;
    assert.equal(current.error, "", JSON.stringify(current));
    assert(current.maximumLabelDistance <= current.labelDistanceLimit + 0.5, JSON.stringify(current));
  }
  assert(Math.max(...returnLatencies) < 2000, `I/O return latency exceeded bound: ${returnLatencies.join(",")}`);

  await dragOneNode(page);
  await waitForOrdinaryLayout(page, generation + 1);
  generation = (await layoutState(page)).generation;

  await dragOneLabel(page);
  await waitForOrdinaryLayout(page, generation + 1);
  const edited = await layoutState(page);
  assert.equal(edited.error, "", JSON.stringify(edited));
  assert(edited.maximumLabelDistance <= edited.labelDistanceLimit + 0.5, JSON.stringify(edited));
  assert.deepEqual(consoleErrors, []);

  await page.screenshot({ path: path.join(outputDirectory, "bounded-ordinary-layout.png"), fullPage: true });
  console.log(JSON.stringify({ initialLatencyMs, returnLatencies, initial, edited }));
  await page.close();
} finally {
  await browser.close();
  await stop(child);
}

console.log("verified bounded ordinary layout, editable placement, and repeated I/O-to-state restoration");
