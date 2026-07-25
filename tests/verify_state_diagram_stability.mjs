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
    } catch {
      // Server is still starting.
    }
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
      && stage.dataset.initialRouteReady === "true";
  });

  const initialIdentity = await page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    stage.dataset.stabilityProbe = "initial";
    return {
      visibility: getComputedStyle(stage).visibility,
      labels: [...stage.querySelectorAll(".edge-label.transition-label")].map(item => item.textContent?.trim()),
    };
  });
  assert.equal(initialIdentity.visibility, "visible");
  assert.equal(initialIdentity.labels.some(label => /^T\d+$/.test(label || "")), false);

  // The base app polls every 900 ms. More than two cycles must not replace the DOM
  // when version/digest/selection are unchanged.
  await page.waitForTimeout(2200);
  const unchanged = await page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return {
      sameStage: stage?.dataset.stabilityProbe === "initial",
      stable: stage?.dataset.renderStable,
      visibility: stage ? getComputedStyle(stage).visibility : null,
    };
  });
  assert.equal(unchanged.sameStage, true, "unchanged polling replaced the committed state graph");
  assert.equal(unchanged.stable, "true");
  assert.equal(unchanged.visibility, "visible");

  // Force a genuine rebuild. The newly inserted base graph must be hidden before
  // label packing, UML semantics, input/action summaries, and initial routing finish.
  const pending = await page.evaluate(() => {
    window.renderState();
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return {
      sameStage: stage?.dataset.stabilityProbe === "initial",
      stable: stage?.dataset.renderStable ?? null,
      visibility: stage ? getComputedStyle(stage).visibility : null,
      labels: [...(stage?.querySelectorAll(".edge-label") || [])].map(item => item.textContent?.trim()),
    };
  });
  assert.equal(pending.sameStage, false, "forced render did not create a new graph stage");
  assert.notEqual(pending.stable, "true");
  assert.equal(pending.visibility, "hidden", "an unadjusted graph became visible");

  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return stage?.dataset.renderStable === "true"
      && stage.dataset.stateTransitionIRV2LabelsReady === "true"
      && stage.dataset.initialRouteReady === "true";
  });
  const committed = await page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return {
      visibility: getComputedStyle(stage).visibility,
      labels: [...stage.querySelectorAll(".edge-label.transition-label")].map(item => item.textContent?.trim()),
      initialPath: Boolean(stage.querySelector(":scope > svg.edge-svg > path.initial-transition-path")),
    };
  });
  assert.equal(committed.visibility, "visible");
  assert.equal(committed.initialPath, true);
  assert.equal(
    committed.labels.some(label => /^T\d+$/.test(label || "")),
    false,
    `raw transition IDs remained visible: ${JSON.stringify(committed.labels)}`,
  );

  await page.screenshot({
    path: path.join(outputDirectory, "stable-state-diagram.png"),
    fullPage: true,
  });
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified atomic state diagram rendering across unchanged polling and a forced rebuild");
