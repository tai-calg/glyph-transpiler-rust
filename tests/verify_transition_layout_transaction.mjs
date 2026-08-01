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
    return Number(stage?.dataset.transitionLayoutGeneration || 0) >= Number(minimum || 0)
      && stage?.dataset.transitionLayoutState === "ready"
      && stage?.dataset.transitionPublicationReady === "true"
      && stage?.dataset.transitionIoClustersReady === "true"
      && stage?.dataset.transitionEnablingCasesReady === "true"
      && stage?.dataset.transitionLayoutProfile === "ordinary";
  }, minimumGeneration, { timeout: 5000 });
}

async function state(page) {
  return page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const clusters = [...(stage?.querySelectorAll(".transition-io-cluster") || [])];
    return {
      layoutState: stage?.dataset.transitionLayoutState || "",
      publicationReady: stage?.dataset.transitionPublicationReady || "",
      layoutProfile: stage?.dataset.transitionLayoutProfile || "",
      layoutMode: stage?.dataset.transitionLayoutMode || "",
      layoutBudgetMs: Number(stage?.dataset.transitionLayoutBudgetMs || 0),
      layoutBudgetExceeded: stage?.dataset.transitionLayoutBudgetExceeded || "",
      renderBudgetMs: Number(stage?.dataset.transitionIoRenderBudgetMs || 0),
      renderDurationMs: Number(stage?.dataset.transitionIoRenderDurationMs || 0),
      denseCanvas: stage?.dataset.transitionDenseCanvas || "",
      generation: Number(stage?.dataset.transitionLayoutGeneration || 0),
      error: stage?.dataset.transitionLayoutError || "",
      transitionCount: clusters.length,
      maxDistance: Math.max(0, ...clusters.map(cluster => Number(cluster.dataset.ioDistance || 0))),
      distanceLimit: Number(stage?.dataset.transitionIoMaxDistance || 0),
      transaction: window.glyphTransitionLayoutTransaction ? {
        version: window.glyphTransitionLayoutTransaction.version,
        profile: window.glyphTransitionLayoutTransaction.profile,
        budgetMs: window.glyphTransitionLayoutTransaction.budgetMs,
        maxFrames: window.glyphTransitionLayoutTransaction.maxFrames,
        maxRetries: window.glyphTransitionLayoutTransaction.maxRetries,
        generation: window.glyphTransitionLayoutTransaction.generation,
        completedGeneration: window.glyphTransitionLayoutTransaction.completedGeneration,
        audit: window.glyphTransitionLayoutTransaction.audit?.(),
      } : null,
      hasCertificate: Boolean(window.glyphLayoutPublicationCertificate),
      hasLegacyRouter: Boolean(window.glyphInitialTransitionRouter),
    };
  });
}

async function dragOneNode(page) {
  const nodes = page.locator(".state-node");
  const deltas = [
    [96, 0], [-96, 0], [0, 96], [0, -96], [72, 72], [-72, 72],
  ];
  for (let index = 0; index < await nodes.count(); index += 1) {
    const node = nodes.nth(index);
    for (const [dx, dy] of deltas) {
      const before = await node.boundingBox();
      if (!before) continue;
      const x = before.x + before.width / 2;
      const y = before.y + before.height / 2;
      await page.mouse.move(x, y);
      await page.mouse.down();
      await page.mouse.move(x + dx, y + dy, { steps: 8 });
      await page.mouse.up();
      await page.waitForTimeout(80);
      const after = await node.boundingBox();
      if (after && (Math.abs(after.x - before.x) > 4 || Math.abs(after.y - before.y) > 4)) {
        await page.waitForFunction(() => Object.keys(localStorage).some(key => key.startsWith("glyph.diagram.positions.v1:")));
        return;
      }
    }
  }
  assert.fail("no state node could be edited");
}

async function dragOneLabel(page) {
  const clusters = page.locator(".transition-io-cluster");
  const deltas = [[28, 0], [-28, 0], [0, 28], [0, -28], [20, 20]];
  for (let index = 0; index < await clusters.count(); index += 1) {
    const cluster = clusters.nth(index);
    for (const [dx, dy] of deltas) {
      const before = await cluster.boundingBox();
      if (!before) continue;
      const x = before.x + before.width / 2;
      const y = before.y + before.height / 2;
      await page.mouse.move(x, y);
      await page.mouse.down();
      await page.mouse.move(x + dx, y + dy, { steps: 6 });
      await page.mouse.up();
      await page.waitForTimeout(80);
      const after = await cluster.boundingBox();
      if (after && (Math.abs(after.x - before.x) > 3 || Math.abs(after.y - before.y) > 3)) {
        await page.waitForFunction(() => Object.keys(localStorage).some(key => key.startsWith("glyph.diagram.transition-io.v1:")));
        return;
      }
    }
  }
  assert.fail("no transition label could be edited");
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

  const start = Date.now();
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await waitForOrdinaryLayout(page);
  const initialLatencyMs = Date.now() - start;
  assert(initialLatencyMs < 5000, `initial state rendering took ${initialLatencyMs}ms`);

  const initial = await state(page);
  assert.equal(initial.layoutState, "ready", JSON.stringify(initial));
  assert.equal(initial.publicationReady, "true", JSON.stringify(initial));
  assert.equal(initial.layoutProfile, "ordinary", JSON.stringify(initial));
  assert.equal(initial.layoutMode, "base", JSON.stringify(initial));
  assert.equal(initial.layoutBudgetMs, 48, JSON.stringify(initial));
  assert.equal(initial.renderBudgetMs, 16, JSON.stringify(initial));
  assert.equal(initial.denseCanvas, "disabled", JSON.stringify(initial));
  assert.equal(initial.error, "", JSON.stringify(initial));
  assert(initial.transitionCount > 0, "no transition labels rendered");
  assert(initial.maxDistance <= initial.distanceLimit + 0.5, JSON.stringify(initial));
  assert.equal(initial.transaction?.version, 8, JSON.stringify(initial));
  assert.equal(initial.transaction?.profile, "ordinary", JSON.stringify(initial));
  assert.equal(initial.transaction?.budgetMs, 48, JSON.stringify(initial));
  assert.equal(initial.transaction?.maxFrames, 2, JSON.stringify(initial));
  assert.equal(initial.transaction?.maxRetries, 0, JSON.stringify(initial));
  assert.equal(initial.transaction?.audit?.ok, true, JSON.stringify(initial));
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
    const current = await state(page);
    generation = current.generation;
    assert.equal(current.error, "", JSON.stringify(current));
    assert.equal(current.layoutState, "ready", JSON.stringify(current));
    assert.equal(current.maxDistance <= current.distanceLimit + 0.5, true, JSON.stringify(current));
  }
  assert(Math.max(...returnLatencies) < 2000, `I/O return latency exceeded bound: ${returnLatencies.join(",")}`);

  await dragOneNode(page);
  await waitForOrdinaryLayout(page, generation + 1);
  generation = (await state(page)).generation;

  await dragOneLabel(page);
  await waitForOrdinaryLayout(page, generation + 1);
  const edited = await state(page);
  assert.equal(edited.error, "", JSON.stringify(edited));
  assert(edited.maxDistance <= edited.distanceLimit + 0.5, JSON.stringify(edited));
  assert.deepEqual(consoleErrors, []);

  await page.screenshot({ path: path.join(outputDirectory, "bounded-ordinary-layout.png"), fullPage: true });
  console.log(JSON.stringify({ initialLatencyMs, returnLatencies, initial, edited }));
  await page.close();
} finally {
  await browser.close();
  await stop(child);
}

console.log("verified bounded ordinary layout, editable placement, and repeated I/O-to-state restoration");
