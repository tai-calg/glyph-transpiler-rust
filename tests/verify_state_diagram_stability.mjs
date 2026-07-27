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
      const response = await fetch(`${url}/api/state`);
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

function assertCommittedIo(identity) {
  assert(identity.clusters.length > 0, "no compact transition I/O was committed");
  for (const cluster of identity.clusters) {
    assert(cluster.io, `${cluster.transitionId}: combined I/O object is missing`);
    assert.equal(cluster.input, null, `${cluster.transitionId}: legacy input object remains`);
    assert.equal(cluster.output, null, `${cluster.transitionId}: legacy output object remains`);
    assert(cluster.distance <= 96.5, `${cluster.transitionId}: I/O escaped its arrow tether`);
    assert(identity.detailIds.includes(cluster.transitionId), `${cluster.transitionId}: no Transition details row`);
  }
  assert.equal(identity.visibleLegacyLabels, 0, "legacy transition labels are visible");
}

function readIdentity() {
  const stage = document.querySelector(".state-node")?.closest(".graph-stage");
  const visibleLegacyLabels = [...stage.querySelectorAll(".transition-label")].filter(item => {
    const style = getComputedStyle(item);
    return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0;
  }).length;
  return {
    visibility: getComputedStyle(stage).visibility,
    clusters: [...stage.querySelectorAll(".transition-io-cluster")].map(item => ({
      transitionId: item.dataset.transitionId || "",
      io: item.querySelector('.transition-io-node[data-io-kind="io"]')?.textContent?.trim(),
      input: item.querySelector('.transition-io-node[data-io-kind="input"]')?.textContent?.trim() ?? null,
      output: item.querySelector('.transition-io-node[data-io-kind="output"]')?.textContent?.trim() ?? null,
      distance: Number(item.dataset.ioDistance || 0),
    })),
    visibleLegacyLabels,
    detailIds: [...document.querySelectorAll(".transition-detail")].map(item => item.dataset.transitionId || ""),
    initialPath: Boolean(stage.querySelector(":scope > svg.edge-svg > path.initial-transition-path")),
  };
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
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return stage?.dataset.renderStable === "true"
      && stage.dataset.labelLayoutReady === "true"
      && stage.dataset.umlTransitionReady === "true"
      && stage.dataset.transitionInputActionLabelsReady === "true"
      && stage.dataset.stateTransitionIRV2LabelsReady === "true"
      && stage.dataset.transitionIoClustersReady === "true"
      && stage.dataset.transitionIoCollisionSolved === "true"
      && stage.dataset.initialRouteReady === "true";
  });

  const initialIdentity = await page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    stage.dataset.stabilityProbe = "initial";
    const visibleLegacyLabels = [...stage.querySelectorAll(".transition-label")].filter(item => {
      const style = getComputedStyle(item);
      return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0;
    }).length;
    return {
      visibility: getComputedStyle(stage).visibility,
      clusters: [...stage.querySelectorAll(".transition-io-cluster")].map(item => ({
        transitionId: item.dataset.transitionId || "",
        io: item.querySelector('.transition-io-node[data-io-kind="io"]')?.textContent?.trim(),
        input: item.querySelector('.transition-io-node[data-io-kind="input"]')?.textContent?.trim() ?? null,
        output: item.querySelector('.transition-io-node[data-io-kind="output"]')?.textContent?.trim() ?? null,
        distance: Number(item.dataset.ioDistance || 0),
      })),
      visibleLegacyLabels,
      detailIds: [...document.querySelectorAll(".transition-detail")].map(item => item.dataset.transitionId || ""),
    };
  });
  assert.equal(initialIdentity.visibility, "visible");
  assertCommittedIo(initialIdentity);

  await page.waitForTimeout(2200);
  const unchanged = await page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return {
      sameStage: stage?.dataset.stabilityProbe === "initial",
      stable: stage?.dataset.renderStable,
      ioReady: stage?.dataset.transitionIoClustersReady,
      visibility: stage ? getComputedStyle(stage).visibility : null,
    };
  });
  assert.equal(unchanged.sameStage, true, "unchanged polling replaced the committed state graph");
  assert.equal(unchanged.stable, "true");
  assert.equal(unchanged.ioReady, "true");
  assert.equal(unchanged.visibility, "visible");

  const pending = await page.evaluate(() => {
    window.renderState();
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return {
      sameStage: stage?.dataset.stabilityProbe === "initial",
      stable: stage?.dataset.renderStable ?? null,
      visibility: stage ? getComputedStyle(stage).visibility : null,
    };
  });
  assert.equal(pending.sameStage, false, "forced render did not create a new graph stage");
  assert.notEqual(pending.stable, "true");
  assert.equal(pending.visibility, "hidden", "an unadjusted graph became visible");

  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return stage?.dataset.renderStable === "true"
      && stage.dataset.stateTransitionIRV2LabelsReady === "true"
      && stage.dataset.transitionIoClustersReady === "true"
      && stage.dataset.transitionIoCollisionSolved === "true"
      && stage.dataset.initialRouteReady === "true";
  });
  const committed = await page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const visibleLegacyLabels = [...stage.querySelectorAll(".transition-label")].filter(item => {
      const style = getComputedStyle(item);
      return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0;
    }).length;
    return {
      visibility: getComputedStyle(stage).visibility,
      clusters: [...stage.querySelectorAll(".transition-io-cluster")].map(item => ({
        transitionId: item.dataset.transitionId || "",
        io: item.querySelector('.transition-io-node[data-io-kind="io"]')?.textContent?.trim(),
        input: item.querySelector('.transition-io-node[data-io-kind="input"]')?.textContent?.trim() ?? null,
        output: item.querySelector('.transition-io-node[data-io-kind="output"]')?.textContent?.trim() ?? null,
        distance: Number(item.dataset.ioDistance || 0),
      })),
      visibleLegacyLabels,
      detailIds: [...document.querySelectorAll(".transition-detail")].map(item => item.dataset.transitionId || ""),
      initialPath: Boolean(stage.querySelector(":scope > svg.edge-svg > path.initial-transition-path")),
    };
  });
  assert.equal(committed.visibility, "visible");
  assert.equal(committed.initialPath, true);
  assertCommittedIo(committed);

  await page.screenshot({
    path: path.join(outputDirectory, "stable-state-diagram.png"),
    fullPage: true,
  });
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified atomic state diagram rendering with compact transition I/O");
