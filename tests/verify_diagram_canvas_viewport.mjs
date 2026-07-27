import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/diagram-canvas-viewport");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`Glyph process exited early\n${logs.join("")}`);
    }
    try {
      const response = await fetch(`${url}/api/state`);
      if (response.ok && (await response.json()).status === "ready") return;
    } catch {
      // The server is still starting.
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

async function drag(page, locator, deltaX, deltaY) {
  const before = await locator.boundingBox();
  assert(before, "drag target has no bounding box");
  const startX = before.x + before.width / 2;
  const startY = before.y + before.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + deltaX, startY + deltaY, { steps: 16 });
  await page.mouse.up();
}

async function viewportAnchor(page, fractionX, fractionY) {
  return page.evaluate(({ fractionX: xFraction, fractionY: yFraction }) => {
    const shell = document.querySelector(".canvas-shell");
    const stage = shell?.querySelector(".graph-stage");
    const surface = stage?.parentElement;
    if (!shell || !stage || !surface) return null;
    const clientX = shell.clientWidth * xFraction;
    const clientY = shell.clientHeight * yFraction;
    const scale = Number.parseFloat(stage.dataset.viewportScale || "1");
    return {
      clientX,
      clientY,
      pageX: shell.getBoundingClientRect().left + clientX,
      pageY: shell.getBoundingClientRect().top + clientY,
      diagramX: (shell.scrollLeft + clientX - surface.offsetLeft) / scale,
      diagramY: (shell.scrollTop + clientY - surface.offsetTop) / scale,
      scale,
    };
  }, { fractionX, fractionY });
}

const logs = [];
const port = 8896;
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
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(() => (
    document.querySelector("#diagram-zoom-out")
    && document.querySelector("#diagram-zoom-in")
    && document.querySelector("#diagram-fit")
    && document.querySelector("#diagram-view-reset")
    && document.querySelector(".graph-stage")?.dataset.viewportScale
    && document.querySelector(".canvas-shell")?.dataset.touchpadZoomReady === "true"
  ));

  assert.equal(await page.locator(".canvas-pan-help").count(), 0);
  assert.equal(await page.locator(".canvas-shell").getAttribute("title"), null);
  assert.equal(await page.locator("#diagram-zoom-value").textContent(), "100%");

  await page.click("#diagram-zoom-out");
  await page.click("#diagram-zoom-out");
  await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.viewportScale === "0.8");
  assert.equal(await page.locator("#diagram-zoom-value").textContent(), "80%");

  const node = page.locator(".state-node").first();
  const beforeLeft = await node.evaluate(element => Number.parseFloat(element.style.left));
  await drag(page, node, 80, 0);
  const afterLeft = await node.evaluate(element => Number.parseFloat(element.style.left));
  assert(
    Math.abs((afterLeft - beforeLeft) - 100) <= 8,
    `zoom-aware node drag moved ${afterLeft - beforeLeft}px instead of about 100px`,
  );

  await page.click("#diagram-view-reset");
  await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.viewportScale === "1");
  const anchorBefore = await viewportAnchor(page, 0.68, 0.42);
  assert(anchorBefore, "missing viewport anchor before pinch");
  await page.locator(".canvas-shell").dispatchEvent("wheel", {
    deltaY: -160,
    deltaMode: 0,
    ctrlKey: true,
    clientX: anchorBefore.pageX,
    clientY: anchorBefore.pageY,
  });
  await page.waitForFunction(() => Number.parseFloat(document.querySelector(".graph-stage")?.dataset.viewportScale || "1") > 1);
  await page.waitForTimeout(80);
  const anchorAfterZoomIn = await viewportAnchor(page, 0.68, 0.42);
  assert(anchorAfterZoomIn.scale > anchorBefore.scale, "touchpad pinch did not zoom in");
  assert(Math.abs(anchorAfterZoomIn.diagramX - anchorBefore.diagramX) < 3, "pinch changed the x anchor");
  assert(Math.abs(anchorAfterZoomIn.diagramY - anchorBefore.diagramY) < 3, "pinch changed the y anchor");

  await page.locator(".canvas-shell").dispatchEvent("wheel", {
    deltaY: 160,
    deltaMode: 0,
    ctrlKey: true,
    clientX: anchorBefore.pageX,
    clientY: anchorBefore.pageY,
  });
  await page.waitForFunction(previous => (
    Number.parseFloat(document.querySelector(".graph-stage")?.dataset.viewportScale || "1") < previous
  ), anchorAfterZoomIn.scale);
  const anchorAfterZoomOut = await viewportAnchor(page, 0.68, 0.42);
  assert(anchorAfterZoomOut.scale < anchorAfterZoomIn.scale, "touchpad pinch did not zoom out");

  await page.click("#diagram-fit");
  await page.waitForFunction(() => sessionStorage.getItem("glyph.diagram.viewport-mode.v1:state:0") === "fit");
  const fitted = await page.evaluate(() => {
    const shell = document.querySelector(".canvas-shell");
    const stage = document.querySelector(".graph-stage");
    const shellRect = shell.getBoundingClientRect();
    const stageRect = stage.getBoundingClientRect();
    return {
      scale: Number.parseFloat(stage.dataset.viewportScale),
      shell: shellRect.toJSON(),
      stage: stageRect.toJSON(),
    };
  });
  assert(fitted.scale >= 0.25 && fitted.scale <= 3);
  assert(fitted.stage.width <= fitted.shell.width - 48 + 2);
  assert(fitted.stage.height <= fitted.shell.height - 48 + 2);

  await page.click("#diagram-view-reset");
  await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.viewportScale === "1");
  assert.equal(await page.locator("#diagram-zoom-value").textContent(), "100%");
  assert.equal(
    await page.evaluate(() => sessionStorage.getItem("glyph.diagram.viewport-mode.v1:state:0")),
    null,
  );

  await page.screenshot({
    path: path.join(outputDirectory, "conveyor-viewport-controls.png"),
    fullPage: true,
  });
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified touchpad pinch zoom, fit-to-screen, reset-view, and zoom-aware dragging");
