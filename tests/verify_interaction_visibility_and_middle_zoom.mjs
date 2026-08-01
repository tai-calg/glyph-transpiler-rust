import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/interaction-visibility-middle-zoom");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(url, child, logs) {
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

async function stopProcess(child) {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    new Promise(resolve => setTimeout(resolve, 1500)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

function transparent(value) {
  return value === "transparent" || value === "rgba(0, 0, 0, 0)";
}

const logs = [];
const browserErrors = [];
const port = 8902;
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
  const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });

  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.waitForFunction(() => window.glyphEditorIdentifierHighlight?.version === 2);

  const candidate = await page.evaluate(() => {
    const editor = document.getElementById("editor");
    const rows = new Map();
    for (const match of editor.value.matchAll(/[A-Za-z_][A-Za-z0-9_]*/g)) {
      const row = rows.get(match[0]) || { token: match[0], indexes: [] };
      row.indexes.push(match.index);
      rows.set(match[0], row);
    }
    return [...rows.values()]
      .filter(row => row.indexes.length >= 2 && row.token.length >= 3)
      .sort((a, b) => b.indexes.length - a.indexes.length || b.token.length - a.token.length)[0];
  });
  assert(candidate, "source does not contain a repeated identifier");

  await page.evaluate(({ token, indexes }) => {
    const editor = document.getElementById("editor");
    editor.focus();
    editor.setSelectionRange(indexes[0], indexes[0] + token.length);
    editor.dispatchEvent(new Event("select", { bubbles: true }));
  }, candidate);
  await page.waitForFunction(({ token, count }) => {
    const editor = document.getElementById("editor");
    return editor.dataset.activeIdentifier === token
      && Number(editor.dataset.identifierMatchCount || 0) === count
      && document.querySelectorAll("#identifier-highlight-layer mark").length === count;
  }, { token: candidate.token, count: candidate.indexes.length });

  const highlightAppearance = await page.evaluate(() => {
    const editor = document.getElementById("editor");
    const surface = document.querySelector(".identifier-highlight-surface");
    const layer = document.getElementById("identifier-highlight-layer");
    const mark = layer?.querySelector("mark");
    return {
      editorColor: getComputedStyle(editor).color,
      editorBackground: getComputedStyle(editor).backgroundColor,
      surfaceBackground: getComputedStyle(surface).backgroundColor,
      layerColor: getComputedStyle(layer).color,
      markColor: getComputedStyle(mark).color,
      markBackground: getComputedStyle(mark).backgroundColor,
      active: editor.parentElement.classList.contains("identifier-highlight-active"),
    };
  });
  assert.equal(highlightAppearance.active, true);
  assert.equal(transparent(highlightAppearance.editorColor), false, "identifier selection hid all editor text");
  assert.equal(transparent(highlightAppearance.editorBackground), false, "identifier selection removed the editor background");
  assert.equal(transparent(highlightAppearance.surfaceBackground), true, "highlight surface covered the whole editor");
  assert.equal(transparent(highlightAppearance.layerColor), true, "nonmatching overlay text is visible");
  assert.equal(transparent(highlightAppearance.markColor), true, "overlay duplicated matching text");
  assert.equal(transparent(highlightAppearance.markBackground), false, "matching identifiers have no highlight background");

  await page.click('button[data-tab="state"]');
  await page.waitForFunction(() => {
    const shell = document.querySelector(".canvas-shell");
    const stage = shell?.querySelector(".graph-stage");
    return stage?.dataset.transitionLayoutState === "ready"
      && stage.dataset.viewportScale
      && shell?.dataset.middleDragZoomReady === "true"
      && window.glyphDiagramMiddleDragZoom?.version === 1;
  }, null, { timeout: 60_000 });

  await page.evaluate(() => window.glyphDiagramViewport.reset());
  await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.viewportScale === "1");
  const shell = page.locator(".canvas-shell");
  const box = await shell.boundingBox();
  assert(box, "diagram canvas has no bounding box");
  const x = box.x + box.width * 0.55;
  const y = box.y + box.height * 0.55;

  await page.mouse.move(x, y);
  await page.mouse.down({ button: "middle" });
  await page.waitForFunction(() => {
    const shell = document.querySelector(".canvas-shell");
    return shell?.classList.contains("glyph-middle-zooming")
      && !shell.classList.contains("glyph-panning")
      && window.glyphDiagramMiddleDragZoom?.active() === true;
  });
  await page.mouse.move(x, y - 120, { steps: 14 });
  await page.mouse.up({ button: "middle" });
  await page.waitForFunction(() => Number.parseFloat(
    document.querySelector(".graph-stage")?.dataset.viewportScale || "1"
  ) > 1);
  const zoomedIn = Number.parseFloat(await page.locator(".graph-stage").getAttribute("data-viewport-scale"));
  assert(zoomedIn > 1, `middle-button upward drag did not zoom in: ${zoomedIn}`);

  await page.mouse.move(x, y);
  await page.mouse.down({ button: "middle" });
  await page.mouse.move(x, y + 150, { steps: 16 });
  await page.mouse.up({ button: "middle" });
  await page.waitForFunction(previous => Number.parseFloat(
    document.querySelector(".graph-stage")?.dataset.viewportScale || "1"
  ) < previous, zoomedIn);
  const zoomedOut = Number.parseFloat(await page.locator(".graph-stage").getAttribute("data-viewport-scale"));
  assert(zoomedOut < zoomedIn, `middle-button downward drag did not zoom out: ${zoomedOut}`);
  assert.equal(await shell.getAttribute("data-middle-drag-zoom-state"), "idle");
  assert.equal(await shell.evaluate(element => element.classList.contains("glyph-middle-zooming")), false);

  await page.screenshot({ path: path.join(outputDirectory, "visible-highlight-middle-zoom.png"), fullPage: true });
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify({
    identifier: candidate.token,
    identifierMatchCount: candidate.indexes.length,
    editorColor: highlightAppearance.editorColor,
    editorBackground: highlightAppearance.editorBackground,
    zoomedIn,
    zoomedOut,
  }));
} finally {
  await browser.close();
  await stopProcess(child);
}
