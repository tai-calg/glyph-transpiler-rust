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

async function dragElement(page, locator, deltaX, deltaY, name) {
  const before = await locator.boundingBox();
  assert(before, `${name} has no bounding box before drag`);
  const startX = before.x + before.width / 2;
  const startY = before.y + before.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + deltaX, startY + deltaY, { steps: 10 });
  await page.mouse.up();
  const after = await locator.boundingBox();
  assert(after, `${name} has no bounding box after drag`);
  assert(Math.abs(after.x - before.x) > 3 || Math.abs(after.y - before.y) > 3, `${name} did not move`);
  return { before, after };
}

async function waitForOrdinaryLayout(page, minimumGeneration = 0) {
  await page.waitForFunction(minimum => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const transaction = window.glyphTransitionLayoutTransaction;
    return stage?.dataset.editorReady === "true"
      && stage?.dataset.transitionIoClustersReady === "true"
      && stage?.dataset.transitionEnablingCasesReady === "true"
      && stage?.dataset.transitionLayoutState === "ready"
      && stage?.dataset.transitionPublicationReady === "true"
      && stage?.dataset.transitionLayoutProfile === "ordinary"
      && stage?.dataset.transitionLayoutMode === "base"
      && stage?.dataset.transitionDenseCanvas === "disabled"
      && !stage?.dataset.transitionLayoutError
      && Number(transaction?.generation || 0) >= Number(minimum || 0)
      && transaction?.generation === transaction?.completedGeneration
      && document.querySelector(".transition-io-cluster")?.dataset.ioDragReady === "true";
  }, minimumGeneration, { timeout: 5000 });
}

async function ioPlacement(locator) {
  return locator.evaluate(element => {
    const left = Number.parseFloat(element.style.left || "0");
    const top = Number.parseFloat(element.style.top || "0");
    const anchorX = Number(element.dataset.anchorX || 0);
    const anchorY = Number(element.dataset.anchorY || 0);
    const stage = element.closest(".graph-stage");
    return {
      left,
      top,
      anchorX,
      anchorY,
      dx: left - anchorX,
      dy: top - anchorY,
      distance: Math.hypot(left - anchorX, top - anchorY),
      manual: element.dataset.manualIo || "",
      publication: stage?.dataset.transitionPublicationReady || "",
      profile: stage?.dataset.transitionLayoutProfile || "",
      error: stage?.dataset.transitionLayoutError || "",
    };
  });
}

async function storedManualPlacement(page, transitionId) {
  return page.evaluate(id => {
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (!key?.startsWith("glyph.diagram.transition-io.v1:")) continue;
      try {
        const value = JSON.parse(localStorage.getItem(key) || "{}");
        if (Object.prototype.hasOwnProperty.call(value, id)) return true;
      } catch {}
    }
    return false;
  }, transitionId);
}

async function dragFeasibleTransitionCluster(page) {
  const all = page.locator(".transition-io-cluster");
  const deltas = [[28, 0], [-28, 0], [0, 28], [0, -28], [20, 20]];
  for (let index = 0; index < await all.count(); index += 1) {
    const initial = all.nth(index);
    const transitionId = await initial.getAttribute("data-transition-id");
    if (!transitionId) continue;
    for (const [dx, dy] of deltas) {
      const cluster = page.locator(`.transition-io-cluster[data-transition-id="${transitionId}"]`);
      const before = await cluster.boundingBox();
      if (!before) continue;
      const generation = await page.evaluate(() => Number(window.glyphTransitionLayoutTransaction?.generation || 0));
      await dragElement(page, cluster, dx, dy, `transition ${transitionId}`);
      await waitForOrdinaryLayout(page, generation + 1);
      const live = page.locator(`.transition-io-cluster[data-transition-id="${transitionId}"]`);
      const placement = await ioPlacement(live);
      if (placement.manual === "true" && await storedManualPlacement(page, transitionId)) {
        assert(placement.distance <= 96.5, "dragged I/O escaped its arrow tether");
        return { cluster: live, transitionId, placement };
      }
    }
  }
  assert.fail("no transition label accepted a manual placement");
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
  assert(await page.locator('.transition-io-node[data-io-kind="io"]').count() > 0);
  assert.equal(await page.locator('.transition-io-node[data-io-kind="input"]').count(), 0);
  assert.equal(await page.locator('.transition-io-node[data-io-kind="output"]').count(), 0);
  assert.equal(await page.locator(".transition-io-cluster.failure-transition,.transition-io-cluster .transition-io-error").count(), 0);
  assert.equal(await page.evaluate(() => Boolean(window.glyphLayoutPublicationCertificate)), false);
  assert.equal(await page.evaluate(() => Boolean(window.glyphInitialTransitionRouter)), false);

  const generationBeforeNode = await page.evaluate(() => Number(window.glyphTransitionLayoutTransaction?.generation || 0));
  await dragElement(page, page.locator(".state-node").first(), 120, 90, "state node");
  await waitForOrdinaryLayout(page, generationBeforeNode + 1);
  assert(await page.evaluate(() => Object.keys(localStorage).some(key => key.startsWith("glyph.diagram.positions.v1:"))), "edited node positions were not persisted");

  const dragged = await dragFeasibleTransitionCluster(page);
  const transitionId = dragged.transitionId;
  const draggedPlacement = dragged.placement;

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await waitForOrdinaryLayout(page);
  const restored = page.locator(`.transition-io-cluster[data-transition-id="${transitionId}"]`);
  await page.waitForFunction(id => document.querySelector(`.transition-io-cluster[data-transition-id="${id}"]`)?.dataset.manualIo === "true", transitionId, { timeout: 3000 });
  const restoredPlacement = await ioPlacement(restored);
  assert.equal(restoredPlacement.manual, "true");
  assert(restoredPlacement.distance <= 96.5, "restored I/O escaped its arrow tether");
  assert(Math.abs(restoredPlacement.dx - draggedPlacement.dx) < 4, "I/O x offset from arrow was not restored");
  assert(Math.abs(restoredPlacement.dy - draggedPlacement.dy) < 4, "I/O y offset from arrow was not restored");

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
      assert(markup.includes("ConveyorStart"), "SVG export omitted transition input labels");
      assert(markup.includes("set_conveyor"), "SVG export omitted operation-derived Action labels");
      assert(markup.includes("➞"), "SVG export omitted the I/O separator");
      assert(!markup.includes(" / "), "SVG export retained the old slash separator");
      assert(markup.includes("transition-io-export-label"), "SVG export omitted readable transition labels");
    }
    assert(bytes.length > 500, `${extension} export is unexpectedly small`);
  }

  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  await page.screenshot({ path: path.join(outputDirectory, "conveyor-monochrome-editor.png"), fullPage: true });
  await page.selectOption("#diagram-theme", "white");
  await page.screenshot({ path: path.join(outputDirectory, "conveyor-white-editor.png"), fullPage: true });
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified fast node/label editing, independent scrolling, themes, and diagram exports");
