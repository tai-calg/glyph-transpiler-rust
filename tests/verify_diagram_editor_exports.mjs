import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/diagram-editor-exports");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph process exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`);
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

async function dragNode(page, locator, deltaX, deltaY) {
  const before = await locator.boundingBox();
  assert(before, "state node has no bounding box before drag");
  const startX = before.x + before.width / 2;
  const startY = before.y + before.height / 2;

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + deltaX, startY + deltaY, { steps: 20 });
  await page.mouse.up();

  await page.waitForFunction(
    ({ x, y }) => {
      const node = document.querySelector(".state-node");
      if (!node) return false;
      const rect = node.getBoundingClientRect();
      const persisted = Object.keys(localStorage).some(key => (
        key.startsWith("glyph.diagram.positions.v1:")
      ));
      return persisted && (Math.abs(rect.x - x) > 20 || Math.abs(rect.y - y) > 20);
    },
    { x: before.x, y: before.y },
  );

  const after = await locator.boundingBox();
  assert(after, "state node has no bounding box after drag");
  return { before, after };
}

const logs = [];
const port = 8894;
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
  const page = await browser.newPage({ viewport: { width: 1800, height: 1200 } });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(() => (
    document.querySelector("#diagram-tools")
    && document.querySelector(".graph-stage")?.dataset.editorReady === "true"
    && document.querySelector(".initial-transition-path")
  ));

  assert.equal(await page.locator("#diagram-svg").count(), 1);
  assert.equal(await page.locator("#diagram-png").count(), 1);
  assert.equal(await page.locator("#diagram-pdf").count(), 1);
  assert.equal(await page.locator("#diagram-theme").inputValue(), "white");

  const node = page.locator(".state-node").first();
  const { before, after } = await dragNode(page, node, 170, 160);
  assert(
    Math.abs(after.x - before.x) > 20 || Math.abs(after.y - before.y) > 20,
    "node did not move",
  );

  const stored = await page.evaluate(() => Object.keys(localStorage).some(
    key => key.startsWith("glyph.diagram.positions.v1:"),
  ));
  assert(stored, "edited node positions were not persisted");

  await page.selectOption("#diagram-theme", "monochrome");
  assert(await page.locator("html").evaluate(
    element => element.classList.contains("theme-monochrome"),
  ));
  const shellBackground = await page.locator(".canvas-shell").evaluate(
    element => getComputedStyle(element).backgroundColor,
  );
  assert.equal(shellBackground, "rgb(255, 255, 255)");

  for (const [button, extension, signature] of [
    ["#diagram-svg", "svg", "<svg"],
    ["#diagram-png", "png", "89504e470d0a1a0a"],
    ["#diagram-pdf", "pdf", "%PDF-1.4"],
  ]) {
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.click(button),
    ]);
    const target = path.join(outputDirectory, `conveyor-export.${extension}`);
    await download.saveAs(target);
    const bytes = await fs.readFile(target);
    if (extension === "png") {
      assert.equal(bytes.subarray(0, 8).toString("hex"), signature);
    } else {
      assert(
        bytes.toString("latin1", 0, 32).startsWith(signature),
        `${extension} signature is invalid`,
      );
    }
    assert(bytes.length > 500, `${extension} export is unexpectedly small`);
  }

  await page.screenshot({
    path: path.join(outputDirectory, "conveyor-monochrome-editor.png"),
    fullPage: true,
  });
  await page.selectOption("#diagram-theme", "white");
  await page.screenshot({
    path: path.join(outputDirectory, "conveyor-white-editor.png"),
    fullPage: true,
  });
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified editable white/monochrome diagrams and SVG/PNG/PDF exports");
