import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/transition-layout-transaction");
await fs.mkdir(outputDirectory, { recursive: true });
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

async function waitForOrdinaryLayout(page) {
  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return document.querySelector(".tab.active")?.dataset.tab === "state"
      && stage?.dataset.transitionLayoutState === "ready"
      && stage.dataset.transitionPublicationReady === "true"
      && stage.dataset.transitionIoClustersReady === "true"
      && stage.dataset.transitionLayoutProfile === "ordinary"
      && stage.dataset.stateDiagramWorkspaceGeometryReady === "true"
      && stage.dataset.initialRouteReady === "true"
      && document.querySelectorAll(".transition-index .transition-detail").length > 0;
  }, null, { timeout: 5000 });
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

function assertOrdinary(current) {
  assert.equal(current.layoutState, "ready", JSON.stringify(current));
  assert.equal(current.publicationReady, "true", JSON.stringify(current));
  assert.equal(current.layoutProfile, "ordinary", JSON.stringify(current));
  assert.equal(current.layoutMode, "base", JSON.stringify(current));
  assert.equal(current.layoutBudgetMs, 48, JSON.stringify(current));
  assert.equal(current.renderBudgetMs, 16, JSON.stringify(current));
  assert.equal(current.denseCanvas, "disabled", JSON.stringify(current));
  assert.equal(current.error, "", JSON.stringify(current));
  assert(current.transitionCount > 0, "no transition labels rendered");
  assert(current.maximumLabelDistance <= current.labelDistanceLimit + 0.5, JSON.stringify(current));
  assert.equal(current.transactionVersion, 8, JSON.stringify(current));
  assert(current.transactionGeneration >= current.completedGeneration, JSON.stringify(current));
  assert.equal(current.workspaceVersion, 2, JSON.stringify(current));
  assert.equal(current.workspaceAudit?.ok, true, JSON.stringify(current));
  assert(current.detailCount > 0, JSON.stringify(current));
  assert.equal(current.initialReady, "true", JSON.stringify(current));
  assert.equal(current.initialCertificate, "ordinary-follow", JSON.stringify(current));
  assert.equal(current.hasCertificate, false, JSON.stringify(current));
  assert.equal(current.hasLegacyRouter, false, JSON.stringify(current));
}

const child = spawn("python3", ["glyph.py", "examples/acceptance/door_controller.glyph"], {
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
  assertOrdinary(initial);

  const returnLatencies = [];
  for (let cycle = 0; cycle < 8; cycle += 1) {
    await page.click('button[data-tab="io"]');
    await page.waitForFunction(() => document.querySelector(".tab.active")?.dataset.tab === "io");
    const returnedAt = Date.now();
    await page.click('button[data-tab="state"]');
    await waitForOrdinaryLayout(page);
    returnLatencies.push(Date.now() - returnedAt);
    assertOrdinary(await layoutState(page));
  }
  assert(Math.max(...returnLatencies) < 2000, `I/O return latency exceeded bound: ${returnLatencies.join(",")}`);
  assert.deepEqual(consoleErrors, []);

  await page.screenshot({ path: path.join(outputDirectory, "bounded-ordinary-layout.png"), fullPage: true });
  console.log(JSON.stringify({ initialLatencyMs, returnLatencies, initial }));
  await page.close();
} finally {
  await browser.close();
  await stop(child);
}

console.log("verified bounded ordinary transaction and repeated I/O-to-state restoration");
