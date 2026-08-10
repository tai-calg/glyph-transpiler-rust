import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const port = 8933;
const url = `http://127.0.0.1:${port}`;
const output = "build/state-diagram-regression/motor-safety-motor.png";
const README_SCALE = 0.58;

async function waitForServer(child, logs) {
  for (let attempt = 0; attempt < 150; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph exited early\n${logs.join("")}`);
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

await fs.mkdir("build/state-diagram-regression", { recursive: true });
const logs = [];
const child = spawn("python3", ["glyph.py", "examples/acceptance/motor_safety.glyph"], {
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
  const errors = [];
  page.on("pageerror", error => errors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });

  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return document.querySelector("#machine-select")?.selectedOptions?.[0]?.textContent === "Motor"
      && stage?.dataset.transitionIoClustersReady === "true"
      && stage?.dataset.transitionEnablingCasesReady === "true"
      && stage?.dataset.transitionLayoutState === "ready"
      && stage?.dataset.transitionPublicationReady === "true"
      && stage?.dataset.transitionLayoutProfile === "ordinary"
      && stage?.dataset.transitionLayoutMode === "base"
      && stage?.dataset.transitionDenseCanvas === "disabled"
      && !stage?.dataset.transitionLayoutError
      && stage.querySelectorAll(".transition-io-cluster").length === 12;
  }, null, { timeout: 5000 });

  await page.evaluate(async scale => {
    if (document.fonts?.ready) await document.fonts.ready;
    const shell = document.querySelector(".canvas-shell");
    const stage = shell?.querySelector(".graph-stage");
    if (!shell || !stage || !window.glyphDiagramViewport) throw new Error("diagram viewport is unavailable");
    window.glyphDiagramViewport.setScale(scale);
  }, README_SCALE);
  await page.waitForFunction(scale => {
    const stage = document.querySelector(".canvas-shell .graph-stage");
    return stage && Math.abs(Number(stage.dataset.viewportScale || 0) - scale) < 0.001;
  }, README_SCALE);

  // setScale preserves the old viewport anchor. README publication instead uses a
  // deterministic stage-center anchor so an earlier 57%/58% auto-fit decision cannot
  // alter the documentation snapshot.
  await page.evaluate(async scale => {
    const shell = document.querySelector(".canvas-shell");
    const stage = shell?.querySelector(".graph-stage");
    const surface = stage?.parentElement;
    if (!shell || !stage || !surface) throw new Error("diagram surface is unavailable");
    const width = Number.parseFloat(stage.style.width || "0") || Number(stage.dataset.viewportLogicalWidth || 0);
    const height = Number.parseFloat(stage.style.height || "0") || Number(stage.dataset.viewportLogicalHeight || 0);
    const center = () => {
      shell.scrollLeft = Math.max(0, surface.offsetLeft + width * scale / 2 - shell.clientWidth / 2);
      shell.scrollTop = Math.max(0, surface.offsetTop + height * scale / 2 - shell.clientHeight / 2);
    };
    center();
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    center();
    await new Promise(resolve => setTimeout(resolve, 80));
    center();
  }, README_SCALE);

  const state = await page.evaluate(() => {
    const shell = document.querySelector(".canvas-shell");
    const stage = shell?.querySelector(".graph-stage");
    return {
      scale: Number(stage?.dataset.viewportScale || 0),
      zoomText: document.getElementById("diagram-zoom-value")?.textContent || "",
      scrollLeft: shell?.scrollLeft || 0,
      scrollTop: shell?.scrollTop || 0,
      stageWidth: Number.parseFloat(stage?.style.width || "0") || 0,
      stageHeight: Number.parseFloat(stage?.style.height || "0") || 0,
      transitions: stage?.querySelectorAll(".transition-io-cluster").length || 0,
    };
  });
  assert.equal(state.scale, README_SCALE, JSON.stringify(state));
  assert.equal(state.zoomText, "58%", JSON.stringify(state));
  assert.equal(state.transitions, 12, JSON.stringify(state));
  assert.deepEqual(errors, [], errors.join("\n"));

  await page.screenshot({ path: output, fullPage: true });
  console.log(JSON.stringify({ deterministicReadmeSnapshot: true, ...state }));
} finally {
  await browser.close();
  await stop(child);
}
