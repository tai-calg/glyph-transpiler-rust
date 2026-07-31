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
      const response = await fetch(`${url}/api/state`);
      if (response.ok && (await response.json()).status === "ready") return;
    } catch {
      // Server is still starting.
    }
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
  const page = await browser.newPage({
    viewport: {width: 1600, height: 1000},
    deviceScaleFactor: 1,
  });
  const browserErrors = [];
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });
  await page.goto(url, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(() => {
    const stage = document.querySelector(".graph-stage");
    return stage?.dataset.transitionLayoutState === "ready"
      && stage?.dataset.initialRouteReady === "true"
      && stage?.dataset.initialRouteCertificate === "valid"
      && stage?.dataset.layoutCertificateState === "valid";
  });

  const first = await page.evaluate(() => {
    const stage = document.querySelector(".graph-stage");
    const initial = stage?.querySelector("path.initial-transition-path");
    return {
      routerVersion: window.glyphInitialTransitionRouter?.version,
      kernelVersion: window.glyphDiagramGeometry?.version,
      certificateVersion: window.glyphLayoutPublicationCertificate?.version,
      candidates: Number(stage?.dataset.initialRouteCandidateCount),
      audited: Number(stage?.dataset.initialRouteAuditedCandidates),
      yields: Number(stage?.dataset.initialRouteYieldCount),
      maxSliceMs: Number(stage?.dataset.initialRouteMaxSliceMs),
      durationMs: Number(stage?.dataset.initialRouteDurationMs),
      clearance: Number(initial?.dataset.routeClearance),
      crossings: Number(initial?.dataset.routeCrossings),
      certificateMaxSliceMs: Number(stage?.dataset.layoutCertificateMaxSliceMs),
      certificateDurationMs: Number(stage?.dataset.layoutCertificateDurationMs),
      certificateTasks: Number(stage?.dataset.layoutCertificateTaskCount),
      kernelCacheHits: Number(window.glyphDiagramGeometry?.statistics?.pathCacheHits || 0),
      kernelCacheMisses: Number(window.glyphDiagramGeometry?.statistics?.pathCacheMisses || 0),
      generation: window.glyphInitialTransitionRouter?.generation,
    };
  });

  assert.equal(first.routerVersion, 2);
  assert.equal(first.kernelVersion, 1);
  assert.equal(first.certificateVersion, 1);
  assert(first.candidates > 0, "candidate bank is empty");
  assert(first.audited > 0, "no quantized candidate was audited");
  assert(first.audited <= first.candidates, "audited candidates exceed the candidate bank");
  assert.equal(first.crossings, 0);
  assert(first.clearance >= 5, `initial route clearance is ${first.clearance}px`);
  assert(first.maxSliceMs <= 32, `initial solver blocked one frame for ${first.maxSliceMs}ms`);
  assert(
    first.certificateMaxSliceMs <= 32,
    `publication certificate blocked one frame for ${first.certificateMaxSliceMs}ms`,
  );
  assert(first.certificateTasks >= 0);

  await page.evaluate(() => {
    document.dispatchEvent(new CustomEvent("glyph-transition-layout-transaction-ready", {
      detail: {reason: "unchanged-performance-probe"},
    }));
  });
  await page.waitForFunction(previous => {
    const stage = document.querySelector(".graph-stage");
    return window.glyphInitialTransitionRouter?.completedGeneration > previous
      && stage?.dataset.initialRouteReady === "true"
      && stage?.dataset.initialRouteCacheHit === "true";
  }, first.generation);
  await page.waitForFunction(() => (
    document.querySelector(".graph-stage")?.dataset.layoutCertificateState === "valid"
  ));

  const repeated = await page.evaluate(() => {
    const stage = document.querySelector(".graph-stage");
    window.glyphLayoutPublicationCertificate?.schedule?.("unchanged-performance-probe", 0);
    return {
      routeCacheHit: stage?.dataset.initialRouteCacheHit,
      routeDurationMs: Number(stage?.dataset.initialRouteDurationMs),
      geometryCacheHits: Number(window.glyphDiagramGeometry?.statistics?.pathCacheHits || 0),
    };
  });
  await page.waitForFunction(() => (
    document.querySelector(".graph-stage")?.dataset.layoutCertificateCacheHit === "true"
  ));
  const certificateCacheHit = await page.evaluate(() => (
    document.querySelector(".graph-stage")?.dataset.layoutCertificateCacheHit
  ));

  assert.equal(repeated.routeCacheHit, "true");
  assert(repeated.routeDurationMs <= 32, `unchanged route reuse took ${repeated.routeDurationMs}ms`);
  assert(repeated.geometryCacheHits >= first.kernelCacheHits);
  assert.equal(certificateCacheHit, "true");
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));

  console.log(JSON.stringify({first, repeated, certificateCacheHit}));
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}
