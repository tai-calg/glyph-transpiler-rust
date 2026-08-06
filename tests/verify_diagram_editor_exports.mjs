import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/diagram-editor-exports");
await fs.mkdir(outputDirectory, { recursive: true });
const port = 8894;
const url = `http://127.0.0.1:${port}`;
const logs = [];

async function waitForServer(child) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
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

async function waitForOrdinaryLayout(page) {
  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return stage?.dataset.editorReady === "true"
      && stage.dataset.transitionIoClustersReady === "true"
      && stage.dataset.transitionLayoutState === "ready"
      && stage.dataset.transitionPublicationReady === "true"
      && stage.dataset.transitionLayoutProfile === "ordinary"
      && stage.dataset.transitionLayoutMode === "base"
      && stage.dataset.transitionDenseCanvas === "disabled"
      && stage.dataset.stateDiagramWorkspaceGeometryReady === "true"
      && stage.dataset.initialRouteReady === "true"
      && !stage.dataset.transitionLayoutError
      && document.querySelector(".transition-io-cluster")?.dataset.ioDragReady === "true";
  }, null, { timeout: 5000 });
}

async function directlyHittablePoint(locator) {
  return locator.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const candidates = [
      [0.5, 0.5], [0.5, 0.25], [0.5, 0.75],
      [0.25, 0.5], [0.75, 0.5],
      [0.25, 0.25], [0.75, 0.25],
      [0.25, 0.75], [0.75, 0.75],
    ];
    for (const [rx, ry] of candidates) {
      const x = rect.left + rect.width * rx;
      const y = rect.top + rect.height * ry;
      const hit = document.elementFromPoint(x, y);
      if (hit && (hit === element || element.contains(hit))) return { x, y };
    }
    return null;
  });
}

async function drag(page, locator, dx, dy, name) {
  const before = await locator.boundingBox();
  assert(before, `${name} has no bounding box`);
  const point = await directlyHittablePoint(locator);
  if (!point) return false;
  await page.mouse.move(point.x, point.y);
  await page.mouse.down();
  await page.mouse.move(point.x + dx, point.y + dy, { steps: 10 });
  await page.mouse.up();
  const after = await locator.boundingBox();
  assert(after, `${name} disappeared after drag`);
  return Math.abs(after.x - before.x) > 3 || Math.abs(after.y - before.y) > 3;
}

async function storedKey(page, prefix) {
  return page.evaluate(value => Array.from(
    { length: localStorage.length },
    (_, index) => localStorage.key(index),
  ).some(key => key?.startsWith(value)), prefix);
}

async function dragNode(page) {
  const nodes = page.locator(".state-node");
  const deltas = [[120, 0], [-120, 0], [0, 120], [0, -120], [88, 88]];
  for (let index = 0; index < await nodes.count(); index += 1) {
    for (const [dx, dy] of deltas) {
      if (!(await drag(page, nodes.nth(index), dx, dy, `state node ${index}`))) continue;
      await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.transitionNodePositions?.startsWith("saved:") === true, null, { timeout: 3000 });
      assert(await storedKey(page, "glyph.diagram.positions.v1:"));
      return;
    }
  }
  assert.fail("no state node accepted an edit");
}

async function dragTransitionLabel(page) {
  const clusters = page.locator(".transition-io-cluster");
  const deltas = [[24, 0], [-24, 0], [0, 24], [0, -24], [18, 18]];
  for (let index = 0; index < await clusters.count(); index += 1) {
    const id = await clusters.nth(index).getAttribute("data-transition-id");
    if (!id) continue;
    for (const [dx, dy] of deltas) {
      const live = page.locator(`.transition-io-cluster[data-transition-id="${id}"]`);
      if (!(await drag(page, live, dx, dy, `transition ${id}`))) continue;
      try {
        await page.waitForFunction(transitionId => document.querySelector(`.transition-io-cluster[data-transition-id="${transitionId}"]`)?.dataset.manualIo === "true", id, { timeout: 1000 });
      } catch {
        continue;
      }
      assert(await storedKey(page, "glyph.diagram.transition-io.v1:"));
      const distance = await live.evaluate(element => Number(element.dataset.ioDistance || 0));
      assert(distance <= 96.5, `transition ${id} escaped its arrow tether`);
      return;
    }
  }
  assert.fail("no transition label accepted an edit");
}

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
  await waitForServer(child);
  const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });
  const browserErrors = [];
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });

  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await waitForOrdinaryLayout(page);

  assert.equal(await page.locator("#diagram-svg").count(), 1);
  assert.equal(await page.locator("#diagram-png").count(), 1);
  assert.equal(await page.locator("#diagram-pdf").count(), 1);
  assert.equal(await page.locator("#diagram-theme").inputValue(), "white");
  assert(await page.locator('.transition-io-cluster .transition-io-node[data-io-kind="io"]').count() > 0);
  assert.equal(await page.locator('.transition-io-cluster .transition-io-node[data-io-kind="input"]').count(), 0);
  assert.equal(await page.locator('.transition-io-cluster .transition-io-node[data-io-kind="output"]').count(), 0);
  assert.equal(await page.locator(".transition-io-cluster .transition-io-error").count(), 0);
  assert(await page.locator(".transition-index .transition-detail").count() > 0);
  assert.equal(await page.evaluate(() => Boolean(window.glyphLayoutPublicationCertificate)), false);
  assert.equal(await page.evaluate(() => Boolean(window.glyphInitialTransitionRouter)), false);

  await dragNode(page);
  await waitForOrdinaryLayout(page);
  await dragTransitionLabel(page);
  await waitForOrdinaryLayout(page);

  const fixedChrome = await page.evaluate(() => {
    const header = document.querySelector("header");
    const viewerHead = document.querySelector(".viewer-head");
    const editor = document.querySelector("#editor");
    const before = { headerTop: header.getBoundingClientRect().top, viewerTop: viewerHead.getBoundingClientRect().top };
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
  assert.equal(fixedChrome.headerTop, fixedChrome.before.headerTop);
  assert.equal(fixedChrome.viewerTop, fixedChrome.before.viewerTop);
  assert(fixedChrome.documentOverflow <= 1);
  assert(fixedChrome.bodyOverflow <= 1);
  assert(fixedChrome.headerOverflow <= 1);
  assert(fixedChrome.viewerHeadOverflow <= 1);
  assert(fixedChrome.toolsOverflow <= 1);

  await page.selectOption("#diagram-theme", "monochrome");
  assert(await page.locator("html").evaluate(element => element.classList.contains("theme-monochrome")));
  assert.equal(await page.locator(".canvas-shell").evaluate(element => getComputedStyle(element).backgroundColor), "rgb(255, 255, 255)");

  for (const [button, extension, signature] of [
    ["#diagram-svg", "svg", "<svg"],
    ["#diagram-png", "png", "89504e470d0a1a0a"],
    ["#diagram-pdf", "pdf", "%PDF-1.4"],
  ]) {
    const [download] = await Promise.all([page.waitForEvent("download"), page.click(button)]);
    const target = path.join(outputDirectory, `conveyor-export.${extension}`);
    await download.saveAs(target);
    const bytes = await fs.readFile(target);
    if (extension === "png") assert.equal(bytes.subarray(0, 8).toString("hex"), signature);
    else assert(bytes.toString("latin1", 0, 32).startsWith(signature), `${extension} signature is invalid`);
    if (extension === "svg") {
      const markup = bytes.toString("utf8");
      assert(markup.includes("ConveyorStart"));
      assert(markup.includes("set_conveyor"));
      assert(markup.includes("➞"));
      assert(markup.includes("transition-io-export-label"));
    }
    assert(bytes.length > 500, `${extension} export is unexpectedly small`);
  }

  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  await page.screenshot({ path: path.join(outputDirectory, "conveyor-monochrome-editor.png"), fullPage: true });
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified node/label editing, transition details, scrolling, themes, and diagram exports");
