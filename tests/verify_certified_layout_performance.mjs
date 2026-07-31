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

async function layoutState(page) {
  return page.evaluate(() => {
    const stage = document.querySelector(".graph-stage");
    return {
      layoutState: stage?.dataset.transitionLayoutState,
      layoutGeneration: stage?.dataset.transitionLayoutGeneration,
      layoutReason: stage?.dataset.transitionLayoutReason,
      routeState: stage?.dataset.initialRouteReady,
      routeCertificate: stage?.dataset.initialRouteCertificate,
      routeSettleState: stage?.dataset.initialRouteSettleState,
      routeSettleDetails: stage?.dataset.initialRouteSettleDetails,
      routeReason: stage?.dataset.initialRouteReason,
      routeCacheHit: stage?.dataset.initialRouteCacheHit,
      routeGeneration: window.glyphInitialTransitionRouter?.generation,
      routeCompletedGeneration: window.glyphInitialTransitionRouter?.completedGeneration,
      routeProtocol: window.glyphInitialTransitionRouter?.layoutGenerationProtocol,
      routeProtocolState: stage?.dataset.initialRouteProtocolState,
      routeProtocolReason: stage?.dataset.initialRouteProtocolReason,
      routeProtocolSequence: stage?.dataset.initialRouteProtocolSequence,
      routeProtocolAttempt: stage?.dataset.initialRouteProtocolAttempt,
      routeProtocolRouterGeneration: stage?.dataset.initialRouteProtocolRouterGeneration,
      certificateState: stage?.dataset.layoutCertificateState,
      certificateRequestState: stage?.dataset.layoutCertificateRequestState,
      certificateReason: stage?.dataset.layoutCertificateReason,
      certificateViolations: stage?.dataset.layoutCertificateViolations,
      certificateCacheHit: stage?.dataset.layoutCertificateCacheHit,
      certificateGeneration: window.glyphLayoutPublicationCertificate?.generation,
      certificateCompletedGeneration: window.glyphLayoutPublicationCertificate?.completedGeneration,
      certificateProtocol: window.glyphLayoutPublicationCertificate?.layoutGenerationProtocol,
      publicationRequest: stage?.dataset.layoutProtocolPublicationRequest,
      publishedGeneration: stage?.dataset.layoutProtocolPublishedGeneration,
      publicationReady: stage?.dataset.transitionPublicationReady,
      dependencyGeneration: window.glyphInitialTransitionDependencyBridge?.settleGeneration,
      dependencySignature: window.glyphInitialTransitionDependencyBridge?.signature,
    };
  });
}

async function waitForCertifiedLayout(page, browserErrors) {
  try {
    await page.waitForFunction(() => {
      const stage = document.querySelector(".graph-stage");
      const routeTerminal = ["true", "failed"].includes(stage?.dataset.initialRouteReady);
      const certificateTerminal = ["valid", "failed"].includes(stage?.dataset.layoutCertificateState);
      return stage?.dataset.transitionLayoutState === "ready" && routeTerminal && certificateTerminal;
    }, undefined, {timeout: 30000});
  } catch (error) {
    const state = await layoutState(page);
    throw new Error(
      `certified layout did not reach a terminal state: ${JSON.stringify(state)}\n`
      + `browser errors: ${JSON.stringify(browserErrors)}\n${error.message}`,
    );
  }
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
  await waitForCertifiedLayout(page, browserErrors);

  const first = await page.evaluate(() => {
    const stage = document.querySelector(".graph-stage");
    const initial = stage?.querySelector("path.initial-transition-path");
    const routerScript = document.getElementById("glyph-initial-transition-routing-v2-script");
    return {
      routerVersion: window.glyphInitialTransitionRouter?.version,
      routerMarker: window.glyphInitialTransitionRouter?.marker || "",
      routerProtocol: window.glyphInitialTransitionRouter?.layoutGenerationProtocol || "",
      routerScheduleName: window.glyphInitialTransitionRouter?.schedule?.name || "",
      routerScriptPresent: Boolean(routerScript),
      routerScriptLength: routerScript?.textContent?.length || 0,
      routerProtocolState: stage?.dataset.initialRouteProtocolState || "",
      routerProtocolReason: stage?.dataset.initialRouteProtocolReason || "",
      routerProtocolSequence: stage?.dataset.initialRouteProtocolSequence || "",
      routerProtocolAttempt: stage?.dataset.initialRouteProtocolAttempt || "",
      routerProtocolGeneration: stage?.dataset.initialRouteProtocolRouterGeneration || "",
      kernelVersion: window.glyphDiagramGeometry?.version,
      renderedPathSampling: window.glyphDiagramGeometry?.renderedPathSampling,
      renderedAdapterVersion: window.glyphDiagramRenderedGeometryAdapter?.version,
      certificateVersion: window.glyphLayoutPublicationCertificate?.version,
      routeState: stage?.dataset.initialRouteReady,
      routeCertificate: stage?.dataset.initialRouteCertificate,
      routeError: stage?.dataset.initialRouteError || "",
      routeFailureDetails: stage?.dataset.initialRouteFailureDetails || "",
      publicationState: stage?.dataset.layoutCertificateState,
      publicationViolations: stage?.dataset.layoutCertificateViolations || "[]",
      publicationMetrics: stage?.dataset.layoutCertificateMetrics || "{}",
      layoutState: stage?.dataset.transitionLayoutState,
      layoutError: stage?.dataset.transitionLayoutError || "",
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

  assert.equal(
    first.routerVersion,
    2,
    `initial router API is unavailable: ${JSON.stringify({first, browserErrors})}`,
  );
  assert(first.kernelVersion >= 2, `rendered geometry kernel version is ${first.kernelVersion}`);
  assert.equal(first.renderedPathSampling, true);
  assert.equal(first.renderedAdapterVersion, 1);
  assert.equal(first.certificateVersion, 1);
  assert.equal(
    first.routeState,
    "true",
    `initial route failed: ${first.routeError} ${first.routeFailureDetails}`,
  );
  assert.equal(first.routeCertificate, "valid");
  assert.equal(
    first.publicationState,
    "valid",
    `publication certificate failed: ${first.publicationViolations} ${first.publicationMetrics}`,
  );
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
  try {
    await page.waitForFunction(previous => {
      const stage = document.querySelector(".graph-stage");
      return window.glyphInitialTransitionRouter?.completedGeneration > previous
        && stage?.dataset.initialRouteReady === "true"
        && stage?.dataset.initialRouteCacheHit === "true";
    }, first.generation, {timeout: 5000});
  } catch (error) {
    const state = await layoutState(page);
    throw new Error(
      `same-generation route reuse did not complete: ${JSON.stringify(state)}\n`
      + `browser errors: ${JSON.stringify(browserErrors)}\n${error.message}`,
    );
  }
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
