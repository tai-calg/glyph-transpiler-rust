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

async function dragElement(page, locator, deltaX, deltaY, name) {
  const before = await locator.boundingBox();
  assert(before, `${name} has no bounding box before drag`);
  const startX = before.x + before.width / 2;
  const startY = before.y + before.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + deltaX, startY + deltaY, { steps: 20 });
  await page.mouse.up();
  const after = await locator.boundingBox();
  assert(after, `${name} has no bounding box after drag`);
  assert(Math.abs(after.x - before.x) > 10 || Math.abs(after.y - before.y) > 10, `${name} did not move`);
  return { before, after };
}

async function ioPlacement(locator) {
  return locator.evaluate(element => {
    const left = Number.parseFloat(element.style.left || "0");
    const top = Number.parseFloat(element.style.top || "0");
    const anchorX = Number(element.dataset.anchorX || 0);
    const anchorY = Number(element.dataset.anchorY || 0);
    return {
      left,
      top,
      anchorX,
      anchorY,
      dx: left - anchorX,
      dy: top - anchorY,
      distance: Math.hypot(left - anchorX, top - anchorY),
      manual: element.dataset.manualIo,
    };
  });
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
  const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  if (!await page.locator('button[data-tab="state"]').evaluate(button => button.classList.contains("active"))) {
    await page.click('button[data-tab="state"]');
  }
  await page.waitForFunction(() => (
    document.querySelector("#diagram-tools")
    && document.querySelector(".graph-stage")?.dataset.editorReady === "true"
    && document.querySelector(".graph-stage")?.dataset.transitionIoCollisionSolved === "true"
    && document.querySelector(".transition-io-cluster")?.dataset.ioDragReady === "true"
    && document.querySelector(".initial-transition-path")
  ));

  assert.equal(await page.locator("#diagram-svg").count(), 1);
  assert.equal(await page.locator("#diagram-png").count(), 1);
  assert.equal(await page.locator("#diagram-pdf").count(), 1);
  assert.equal(await page.locator("#diagram-theme").inputValue(), "white");
  assert(await page.locator('.transition-io-node[data-io-kind="io"]').count() > 0);
  assert.equal(await page.locator('.transition-io-node[data-io-kind="input"]').count(), 0);
  assert.equal(await page.locator('.transition-io-node[data-io-kind="output"]').count(), 0);
  assert.equal(await page.locator(".transition-io-cluster.failure-transition,.transition-io-cluster .transition-io-error").count(), 0);

  const node = page.locator(".state-node").first();
  await dragElement(page, node, 170, 160, "state node");
  await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.transitionIoCollisionSolved === "true");
  await page.waitForTimeout(220);
  const nodeStored = await page.evaluate(() => Object.keys(localStorage).some(
    key => key.startsWith("glyph.diagram.positions.v1:"),
  ));
  assert(nodeStored, "edited node positions were not persisted");

  const collisions = await page.evaluate(() => {
    const visible = element => {
      const style = getComputedStyle(element);
      return style.display !== "none" && style.visibility !== "hidden";
    };
    const clusters = [...document.querySelectorAll(".transition-io-cluster")].filter(visible);
    const nodes = [...document.querySelectorAll(".state-node")].filter(visible);
    const overlaps = (a, b) => !(
      a.right + 2 <= b.left || b.right + 2 <= a.left
      || a.bottom + 2 <= b.top || b.bottom + 2 <= a.top
    );
    let clusterPairs = 0;
    let clusterNodes = 0;
    clusters.forEach((cluster, index) => {
      const rect = cluster.getBoundingClientRect();
      clusters.slice(index + 1).forEach(other => {
        if (overlaps(rect, other.getBoundingClientRect())) clusterPairs += 1;
      });
      nodes.forEach(item => {
        if (overlaps(rect, item.getBoundingClientRect())) clusterNodes += 1;
      });
    });
    return { clusterPairs, clusterNodes };
  });
  assert.equal(collisions.clusterPairs, 0, "transition I/O objects overlap after node movement");
  assert.equal(collisions.clusterNodes, 0, "transition I/O objects overlap state nodes after node movement");

  const cluster = page.locator(".transition-io-cluster").first();
  const transitionId = await cluster.getAttribute("data-transition-id");
  assert(transitionId, "transition I/O cluster has no stable id");
  const tangent = await cluster.evaluate(element => {
    const left = Number.parseFloat(element.style.left || "0");
    const top = Number.parseFloat(element.style.top || "0");
    const anchorX = Number(element.dataset.anchorX || 0);
    const anchorY = Number(element.dataset.anchorY || 0);
    const dx = left - anchorX;
    const dy = top - anchorY;
    const length = Math.hypot(dx, dy);
    if (length < 1) return { x: 36, y: 0 };
    return { x: -dy / length * 36, y: dx / length * 36 };
  });
  await dragElement(page, cluster, tangent.x, tangent.y, "transition I/O cluster");
  await page.waitForFunction(() => Object.keys(localStorage).some(
    key => key.startsWith("glyph.diagram.transition-io.v1:"),
  ));
  await page.waitForFunction(id => (
    document.querySelector(`.transition-io-cluster[data-transition-id="${id}"]`)?.dataset.manualIo === "true"
  ), transitionId);
  const draggedPlacement = await ioPlacement(cluster);
  assert(draggedPlacement.distance <= 96.5, "dragged I/O escaped its arrow tether");

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  const stateTab = page.locator('button[data-tab="state"]');
  if (!await stateTab.evaluate(button => button.classList.contains("active"))) await stateTab.click();
  const restored = page.locator(`.transition-io-cluster[data-transition-id="${transitionId}"]`);
  await page.waitForFunction(id => {
    const element = document.querySelector(`.transition-io-cluster[data-transition-id="${id}"]`);
    return element?.dataset.manualIo === "true"
      && element.dataset.anchorX !== undefined
      && element.dataset.anchorY !== undefined
      && element.closest(".graph-stage")?.dataset.transitionIoCollisionSolved === "true";
  }, transitionId);
  await page.waitForTimeout(220);
  const restoredPlacement = await ioPlacement(restored);
  assert.equal(restoredPlacement.manual, "true");
  assert(restoredPlacement.distance <= 96.5, "restored I/O escaped its arrow tether");
  assert(Math.abs(restoredPlacement.dx - draggedPlacement.dx) < 4, "I/O x offset from arrow was not restored");
  assert(Math.abs(restoredPlacement.dy - draggedPlacement.dy) < 4, "I/O y offset from arrow was not restored");

  const fixedChrome = await page.evaluate(() => {
    const header = document.querySelector("header");
    const viewerHead = document.querySelector(".viewer-head");
    const editor = document.querySelector("#editor");
    const before = {
      headerTop: header.getBoundingClientRect().top,
      viewerTop: viewerHead.getBoundingClientRect().top,
    };
    editor.value += `\n${Array.from({ length: 260 }, (_, index) => `# scroll row ${index + 1}`).join("\n")}`;
    if (typeof syncLines === "function") syncLines();
    editor.scrollTop = editor.scrollHeight;
    return {
      before,
      editorScrollTop: editor.scrollTop,
      headerTop: header.getBoundingClientRect().top,
      viewerTop: viewerHead.getBoundingClientRect().top,
      documentOverflow: document.documentElement.scrollHeight - window.innerHeight,
      bodyOverflow: document.body.scrollHeight - window.innerHeight,
      headerOverflow: header.scrollWidth - header.clientWidth,
      viewerHeadOverflow: viewerHead.scrollWidth - viewerHead.clientWidth,
      toolsOverflow: document.querySelector("#diagram-tools").scrollWidth - document.querySelector("#diagram-tools").clientWidth,
    };
  });
  assert(fixedChrome.editorScrollTop > 0, "source editor is not independently scrollable");
  assert.equal(fixedChrome.headerTop, fixedChrome.before.headerTop, "compile/save header moved with editor scroll");
  assert.equal(fixedChrome.viewerTop, fixedChrome.before.viewerTop, "preview toolbar moved with editor scroll");
  assert(fixedChrome.documentOverflow <= 1, "document created a global vertical scroll area");
  assert(fixedChrome.bodyOverflow <= 1, "body created a global vertical scroll area");
  assert(fixedChrome.headerOverflow <= 1, "compile/save controls overflow the header");
  assert(fixedChrome.viewerHeadOverflow <= 1, "preview controls overflow their toolbar");
  assert(fixedChrome.toolsOverflow <= 1, "export controls overflow their toolbar");

  const independent = await page.evaluate(() => {
    const editor = document.querySelector("#editor");
    const body = document.querySelector(".view-body");
    const spacer = document.createElement("div");
    spacer.id = "scroll-test-spacer";
    spacer.style.height = "900px";
    body.appendChild(spacer);
    const editorBefore = editor.scrollTop;
    body.scrollTop = body.scrollHeight;
    const result = { editorBefore, editorAfter: editor.scrollTop, previewScrollTop: body.scrollTop };
    spacer.remove();
    return result;
  });
  assert(independent.previewScrollTop > 0, "preview pane is not independently scrollable");
  assert.equal(independent.editorAfter, independent.editorBefore, "preview scroll changed editor scroll position");

  await page.selectOption("#diagram-theme", "monochrome");
  assert(await page.locator("html").evaluate(element => element.classList.contains("theme-monochrome")));
  const shellBackground = await page.locator(".canvas-shell").evaluate(element => getComputedStyle(element).backgroundColor);
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
      assert(bytes.toString("latin1", 0, 32).startsWith(signature), `${extension} signature is invalid`);
    }
    if (extension === "svg") {
      const markup = bytes.toString("utf8");
      assert(markup.includes("set_conveyor"), "SVG export omitted transition effect");
      assert(markup.includes(" / "), "SVG export omitted combined input/effect notation");
    }
    assert(bytes.length > 500, `${extension} export is unexpectedly small`);
  }

  await page.screenshot({ path: path.join(outputDirectory, "conveyor-monochrome-editor.png"), fullPage: true });
  await page.selectOption("#diagram-theme", "white");
  await page.screenshot({ path: path.join(outputDirectory, "conveyor-white-editor.png"), fullPage: true });
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified independent scrolling, compact arrow-tethered I/O, themes, and diagram exports");
