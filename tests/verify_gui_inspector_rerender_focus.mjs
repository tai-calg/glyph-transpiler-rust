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

const logs = [];
const browserErrors = [];
const port = 8907;
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
  const page = await browser.newPage({ viewport: { width: 1200, height: 820 } });
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready"
    && window.glyphDiagramGuiUxGuard?.version === 4
    && window.glyphDiagramIdentityStamp?.version === 1);
  await page.locator('.tab[data-tab="state"]').click();
  await page.waitForFunction(() => {
    const stage = document.querySelector(".transition-io-cluster")?.closest(".graph-stage");
    return stage?.dataset.transitionLayoutState === "ready"
      && stage?.dataset.diagramDigest
      && document.querySelectorAll(".transition-io-cluster").length > 0;
  }, null, { timeout: 60_000 });

  const identity = await page.locator(".transition-io-cluster").first().evaluate(cluster => ({
    id: cluster.dataset.transitionId || "",
    digest: cluster.closest(".graph-stage")?.dataset.diagramDigest || "",
  }));
  assert(identity.id, "transition inspector fixture has no transition id");
  assert(identity.digest, "transition inspector fixture has no diagram digest");

  await page.locator(".transition-io-cluster").first().focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => !document.querySelector(".transition-label-inspector")?.hidden
    && document.activeElement?.classList.contains("transition-label-inspector-close"));

  const replacement = await page.evaluate(({ id, digest }) => {
    const oldCluster = [...document.querySelectorAll(".transition-io-cluster")].find(item => item.dataset.transitionId === id);
    if (!oldCluster) throw new Error("transition opener disappeared before replacement");
    const next = oldCluster.cloneNode(true);
    next.dataset.inspectorRerenderReplacement = "true";
    delete next.dataset.guiUxInspectorReady;
    oldCluster.replaceWith(next);
    return {
      oldConnectedImmediately: oldCluster.isConnected,
      replacementConnected: next.isConnected,
      replacementDigest: next.closest(".graph-stage")?.dataset.diagramDigest || "",
      inspectorStillOpen: !document.querySelector(".transition-label-inspector")?.hidden,
      digest,
    };
  }, identity);
  assert.equal(replacement.oldConnectedImmediately, false, "original transition opener remained connected after DOM replacement");
  assert.equal(replacement.replacementConnected, true, "replacement transition opener is not connected");
  assert.equal(replacement.replacementDigest, identity.digest, "replacement transition opener changed diagram identity");
  assert.equal(replacement.inspectorStillOpen, true, "DOM replacement unexpectedly closed the transition inspector");

  await page.waitForFunction(({ id, digest }) => {
    const replacementCluster = [...document.querySelectorAll(".transition-io-cluster")].find(item => (
      item.dataset.transitionId === id && item.dataset.inspectorRerenderReplacement === "true"
    ));
    return replacementCluster
      && replacementCluster.dataset.guiUxInspectorReady === "true"
      && replacementCluster.closest(".graph-stage")?.dataset.diagramDigest === digest;
  }, identity, { timeout: 10_000 });

  await page.keyboard.press("Escape");
  await page.waitForFunction(({ id, digest }) => {
    const active = document.activeElement;
    return document.querySelector(".transition-label-inspector")?.hidden === true
      && active?.classList?.contains("transition-io-cluster")
      && active.dataset.transitionId === id
      && active.dataset.inspectorRerenderReplacement === "true"
      && active.closest(".graph-stage")?.dataset.diagramDigest === digest;
  }, identity, { timeout: 10_000 });

  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify({
    transitionId: identity.id,
    diagramDigest: identity.digest,
    originalOpenerDisconnected: true,
    replacementOpenerBound: true,
    inspectorRemainedOpenAcrossReplacement: true,
    replacementOpenerFocusRestored: true,
  }));
} finally {
  await browser.close();
  await stopProcess(child);
}
