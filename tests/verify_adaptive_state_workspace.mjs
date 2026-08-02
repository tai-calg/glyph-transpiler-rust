import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/adaptive-state-workspace");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`, { cache: "no-store" });
      if (response.ok) {
        const state = await response.json();
        if (state.status === "ready") return state;
      }
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

const port = 8798;
const logs = [];
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
  const url = `http://127.0.0.1:${port}`;
  const state = await waitForServer(url, child, logs);
  const machine = state.views.state.machines.find(item => item.name === "Door") || state.views.state.machines[0];
  assert(machine, "Door machine missing");
  assert(machine.transitions.length >= 8, "fixture is no longer dense enough for adaptive layout");

  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  const errors = [];
  page.on("pageerror", error => errors.push(`pageerror: ${error.message}`));
  page.on("console", message => { if (message.type() === "error") errors.push(`console: ${message.text()}`); });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(expectedCount => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return stage?.dataset.stateDiagramWorkspaceGeometryReady === "true"
      && stage?.dataset.transitionPublicationReady === "true"
      && stage?.dataset.initialRouteReady === "true"
      && stage?.querySelectorAll(".transition-io-cluster").length === expectedCount;
  }, machine.transitions.length, { timeout: 8000 });

  const audit = await page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const dot = stage?.querySelector(".initial-dot");
    const initialPath = stage?.querySelector("path.initial-transition-path");
    const rect = element => {
      const value = element.getBoundingClientRect();
      return { left: value.left, top: value.top, right: value.right, bottom: value.bottom, width: value.width, height: value.height };
    };
    const overlaps = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
    const dotRect = dot ? rect(dot) : null;
    const obstacles = [...(stage?.querySelectorAll(".state-node,.transition-io-cluster") || [])]
      .filter(element => element !== dot)
      .map(element => ({ kind: element.className, rect: rect(element) }));
    const logicalCenters = [...(stage?.querySelectorAll(".state-node") || [])].map(element => ({
      x: element.offsetLeft + element.offsetWidth / 2,
      y: element.offsetTop + element.offsetHeight / 2,
    }));
    const logicalSpanX = logicalCenters.length
      ? Math.max(...logicalCenters.map(item => item.x)) - Math.min(...logicalCenters.map(item => item.x))
      : 0;
    const logicalSpanY = logicalCenters.length
      ? Math.max(...logicalCenters.map(item => item.y)) - Math.min(...logicalCenters.map(item => item.y))
      : 0;
    const stageRect = stage ? rect(stage) : null;
    return {
      present: Boolean(stage && dot && initialPath),
      adaptive: stage?.dataset.stateDiagramWorkspaceAdaptive || "",
      spreadX: Number(stage?.dataset.stateDiagramWorkspaceSpreadX || 0),
      spreadY: Number(stage?.dataset.stateDiagramWorkspaceSpreadY || 0),
      originalWidth: Number(stage?.dataset.stateDiagramWorkspaceOriginalWidth || 0),
      contentWidth: Number(stage?.dataset.stateDiagramWorkspaceContentWidth || 0),
      originalHeight: Number(stage?.dataset.stateDiagramWorkspaceOriginalHeight || 0),
      contentHeight: Number(stage?.dataset.stateDiagramWorkspaceContentHeight || 0),
      initialCertificate: stage?.dataset.initialRouteCertificate || "",
      initialCollisions: Number(stage?.dataset.initialRouteCollisionCount || -1),
      initialDotCollisions: Number(stage?.dataset.initialRouteDotCollisionCount || -1),
      initialPathCollisions: Number(stage?.dataset.initialRoutePathCollisionCount || -1),
      actualDotOverlaps: dotRect ? obstacles.filter(item => overlaps(dotRect, item.rect)).length : -1,
      dotInside: Boolean(dotRect && stageRect && dotRect.left >= stageRect.left && dotRect.top >= stageRect.top && dotRect.right <= stageRect.right && dotRect.bottom <= stageRect.bottom),
      pathData: initialPath?.getAttribute("d") || "",
      logicalSpanX,
      logicalSpanY,
    };
  });

  await page.screenshot({ path: path.join(outputDirectory, "door-adaptive-layout.png"), fullPage: true });
  await fs.writeFile(path.join(outputDirectory, "audit.json"), JSON.stringify(audit, null, 2));

  assert.equal(audit.present, true, JSON.stringify(audit));
  assert.equal(audit.adaptive, "true", JSON.stringify(audit));
  assert(audit.spreadX >= 1.35, JSON.stringify(audit));
  assert(audit.spreadY >= 1.1, JSON.stringify(audit));
  assert(audit.contentWidth > audit.originalWidth * 1.3, JSON.stringify(audit));
  assert(audit.contentHeight > audit.originalHeight * 1.05, JSON.stringify(audit));
  assert(audit.logicalSpanX >= 560, JSON.stringify(audit));
  assert(audit.logicalSpanY >= 420, JSON.stringify(audit));
  assert.equal(audit.initialCertificate, "ordinary-obstacle-free", JSON.stringify(audit));
  assert.equal(audit.initialCollisions, 0, JSON.stringify(audit));
  assert.equal(audit.initialDotCollisions, 0, JSON.stringify(audit));
  assert.equal(audit.initialPathCollisions, 0, JSON.stringify(audit));
  assert.equal(audit.actualDotOverlaps, 0, JSON.stringify(audit));
  assert.equal(audit.dotInside, true, JSON.stringify(audit));
  assert.match(audit.pathData, /^M\s/);
  assert.deepEqual(errors, [], errors.join("\n"));
  await page.close();
} finally {
  await browser.close();
  await stop(child);
}

console.log("verified adaptive dense-state spacing and collision-free initial marker routing");
