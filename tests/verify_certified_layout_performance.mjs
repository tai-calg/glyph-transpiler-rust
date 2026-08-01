import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const source = "examples/state_diagrams/conveyor_control.glyph";
const port = 8896;
const logs = [];

async function waitForServer(url, child) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`Glyph process exited early (${child.exitCode})\n${logs.join("")}`);
    }
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

async function layoutState(page) {
  return page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const transaction = window.glyphTransitionLayoutTransaction;
    const clusters = [...(stage?.querySelectorAll(".transition-io-cluster") || [])];
    return {
      layoutState: stage?.dataset.transitionLayoutState || "",
      publicationReady: stage?.dataset.transitionPublicationReady || "",
      layoutProfile: stage?.dataset.transitionLayoutProfile || "",
      layoutMode: stage?.dataset.transitionLayoutMode || "",
      layoutReason: stage?.dataset.transitionLayoutReason || "",
      layoutGeneration: Number(stage?.dataset.transitionLayoutGeneration || 0),
      layoutBudgetMs: Number(stage?.dataset.transitionLayoutBudgetMs || 0),
      renderBudgetMs: Number(stage?.dataset.transitionIoRenderBudgetMs || 0),
      renderDurationMs: Number(stage?.dataset.transitionIoRenderDurationMs || 0),
      renderBudgetExceeded: stage?.dataset.transitionIoRenderBudgetExceeded || "",
      denseCanvas: stage?.dataset.transitionDenseCanvas || "",
      error: stage?.dataset.transitionLayoutError || "",
      transitionCount: clusters.length,
      maximumLabelDistance: Math.max(0, ...clusters.map(cluster => Number(cluster.dataset.ioDistance || 0))),
      labelDistanceLimit: Number(stage?.dataset.transitionIoMaxDistance || 0),
      transactionVersion: Number(transaction?.version || 0),
      transactionProfile: transaction?.profile || "",
      transactionBudgetMs: Number(transaction?.budgetMs || 0),
      maxFrames: Number(transaction?.maxFrames || 0),
      maxRetries: Number(transaction?.maxRetries ?? -1),
      requestedGeneration: Number(transaction?.generation || 0),
      completedGeneration: Number(transaction?.completedGeneration || 0),
      audit: transaction?.audit?.() || null,
      geometryKernelVersion: Number(window.glyphDiagramGeometry?.version || 0),
      renderedAdapterVersion: Number(window.glyphDiagramRenderedGeometryAdapter?.version || 0),
      certificatePresent: Boolean(window.glyphLayoutPublicationCertificate),
      initialRouterPresent: Boolean(window.glyphInitialTransitionRouter),
    };
  });
}

const child = spawn("python3", ["glyph.py", source], {
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

const url = `http://127.0.0.1:${port}`;
const browser = await chromium.launch({ headless: true });
try {
  await waitForServer(url, child);
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  const browserErrors = [];
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });

  const initialStarted = Date.now();
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await waitForOrdinaryLayout(page);
  const initialLatencyMs = Date.now() - initialStarted;

  const first = await layoutState(page);
  assert(initialLatencyMs < 5000, `initial layout took ${initialLatencyMs}ms`);
  assert.equal(first.layoutState, "ready", JSON.stringify(first));
  assert.equal(first.publicationReady, "true", JSON.stringify(first));
  assert.equal(first.layoutProfile, "ordinary", JSON.stringify(first));
  assert.equal(first.layoutMode, "base", JSON.stringify(first));
  assert.equal(first.layoutBudgetMs, 48, JSON.stringify(first));
  assert.equal(first.renderBudgetMs, 16, JSON.stringify(first));
  assert.equal(first.denseCanvas, "disabled", JSON.stringify(first));
  assert.equal(first.error, "", JSON.stringify(first));
  assert(first.transitionCount > 0, "no transitions rendered");
  assert(first.maximumLabelDistance <= first.labelDistanceLimit + 0.5, JSON.stringify(first));
  assert.equal(first.transactionVersion, 8, JSON.stringify(first));
  assert.equal(first.transactionProfile, "ordinary", JSON.stringify(first));
  assert.equal(first.transactionBudgetMs, 48, JSON.stringify(first));
  assert.equal(first.maxFrames, 2, JSON.stringify(first));
  assert.equal(first.maxRetries, 0, JSON.stringify(first));
  assert.equal(first.audit?.ok, true, JSON.stringify(first));
  assert(first.geometryKernelVersion >= 2, JSON.stringify(first));
  assert.equal(first.renderedAdapterVersion, 1, JSON.stringify(first));
  assert.equal(first.certificatePresent, false, JSON.stringify(first));
  assert.equal(first.initialRouterPresent, false, JSON.stringify(first));

  const burstStarted = Date.now();
  const requested = await page.evaluate(() => {
    let generation = 0;
    for (let index = 0; index < 20; index += 1) {
      generation = window.glyphTransitionLayoutTransaction.schedule(`performance-burst-${index}`, 0);
    }
    return generation;
  });
  await waitForOrdinaryLayout(page, requested);
  const burstLatencyMs = Date.now() - burstStarted;
  const repeated = await layoutState(page);

  assert(burstLatencyMs < 1000, `coalesced 20-request burst took ${burstLatencyMs}ms`);
  assert.equal(repeated.layoutGeneration, requested, JSON.stringify(repeated));
  assert.equal(repeated.requestedGeneration, requested, JSON.stringify(repeated));
  assert(repeated.completedGeneration >= requested, JSON.stringify(repeated));
  assert.equal(repeated.error, "", JSON.stringify(repeated));
  assert(repeated.maximumLabelDistance <= repeated.labelDistanceLimit + 0.5, JSON.stringify(repeated));
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));

  console.log(JSON.stringify({ initialLatencyMs, burstLatencyMs, first, repeated }));
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}
