import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const port = 8875;
const url = `http://127.0.0.1:${port}`;
const outputDirectory = path.resolve("build/state-diagram-stability");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(child, logs) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`Glyph diagram process exited early (${child.exitCode})\n${logs.join("")}`);
    }
    try {
      const response = await fetch(`${url}/api/state`, { cache: "no-store" });
      if (response.ok && (await response.json()).status === "ready") return;
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Glyph diagram server did not become ready\n${logs.join("")}`);
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

async function waitForCommitted(page) {
  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return document.querySelector(".tab.active")?.dataset.tab === "state"
      && stage?.dataset.transitionLayoutState === "ready"
      && stage.dataset.transitionPublicationReady === "true"
      && stage.dataset.transitionIoClustersReady === "true"
      && stage.dataset.stateDiagramWorkspaceGeometryReady === "true"
      && stage.dataset.initialRouteReady === "true"
      && document.querySelectorAll(".transition-index .transition-detail").length > 0;
  }, null, { timeout: 5000 });
}

async function identity(page, marker = "") {
  return page.evaluate(value => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    if (value) stage.dataset.stabilityProbe = value;
    const visibleLegacyLabels = [...stage.querySelectorAll(".transition-label")].filter(item => {
      const style = getComputedStyle(item);
      return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0;
    }).length;
    return {
      marker: stage.dataset.stabilityProbe || "",
      visibility: getComputedStyle(stage).visibility,
      width: Number.parseFloat(stage.style.width || "0") || 0,
      height: Number.parseFloat(stage.style.height || "0") || 0,
      layoutState: stage.dataset.transitionLayoutState || "",
      publicationReady: stage.dataset.transitionPublicationReady || "",
      initialReady: stage.dataset.initialRouteReady || "",
      initialCertificate: stage.dataset.initialRouteCertificate || "",
      initialPath: Boolean(stage.querySelector(":scope > svg.edge-svg > path.initial-transition-path")),
      clusters: [...stage.querySelectorAll(".transition-io-cluster")].map(item => ({
        transitionId: item.dataset.transitionId || "",
        io: item.querySelector('.transition-io-node[data-io-kind="io"]')?.textContent?.trim(),
        input: item.querySelector('.transition-io-node[data-io-kind="input"]')?.textContent?.trim() ?? null,
        output: item.querySelector('.transition-io-node[data-io-kind="output"]')?.textContent?.trim() ?? null,
        distance: Number(item.dataset.ioDistance || 0),
      })),
      visibleLegacyLabels,
      detailIds: [...document.querySelectorAll(".transition-index .transition-detail")]
        .map(item => item.dataset.transitionId || ""),
    };
  }, marker);
}

function assertCommitted(current) {
  assert.equal(current.visibility, "visible");
  assert.equal(current.layoutState, "ready");
  assert.equal(current.publicationReady, "true");
  assert.equal(current.initialReady, "true");
  assert.equal(current.initialCertificate, "ordinary-follow");
  assert.equal(current.initialPath, true);
  assert(current.width >= 1600, `workspace width is ${current.width}`);
  assert(current.height >= 960, `workspace height is ${current.height}`);
  assert(current.clusters.length > 0, "no compact transition I/O was committed");
  assert.equal(current.visibleLegacyLabels, 0, "legacy transition labels are visible");
  for (const cluster of current.clusters) {
    assert(cluster.io, `${cluster.transitionId}: combined I/O object is missing`);
    assert.equal(cluster.input, null, `${cluster.transitionId}: legacy input object remains`);
    assert.equal(cluster.output, null, `${cluster.transitionId}: legacy output object remains`);
    assert(cluster.distance <= 96.5, `${cluster.transitionId}: I/O escaped its arrow tether`);
    assert(current.detailIds.includes(cluster.transitionId), `${cluster.transitionId}: no transition detail row`);
  }
}

const logs = [];
const child = spawn("python3", ["glyph.py", "examples/state_diagrams/traffic_light.glyph"], {
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
  await waitForServer(child, logs);
  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  const browserErrors = [];
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });

  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await waitForCommitted(page);

  const initial = await identity(page, "initial");
  assertCommitted(initial);

  await page.waitForTimeout(2200);
  const unchanged = await identity(page);
  assert.equal(unchanged.marker, "initial", "unchanged polling replaced the committed state graph");
  assertCommitted(unchanged);
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));

  await page.screenshot({
    path: path.join(outputDirectory, "stable-state-diagram.png"),
    fullPage: true,
  });
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified stable ordinary workspace, transition details, and unchanged polling");
