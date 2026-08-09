import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/gui-interaction-completeness");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 200; attempt += 1) {
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

const logs = [];
const browserErrors = [];
const requests = [];
const port = 8904;
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
  const page = await browser.newPage({ viewport: { width: 1200, height: 820 } });
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });
  page.on("request", request => requests.push({ method: request.method(), url: request.url() }));
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready"
    && window.glyphDiagramGuiUxGuard?.version === 1);

  const tabContract = await page.evaluate(() => ({
    listRole: document.querySelector(".tabs")?.getAttribute("role"),
    ioRole: document.querySelector('.tab[data-tab="io"]')?.getAttribute("role"),
    ioSelected: document.querySelector('.tab[data-tab="io"]')?.getAttribute("aria-selected"),
    stateSelected: document.querySelector('.tab[data-tab="state"]')?.getAttribute("aria-selected"),
  }));
  assert.equal(tabContract.listRole, "tablist");
  assert.equal(tabContract.ioRole, "tab");
  assert.equal(tabContract.ioSelected, "true");
  assert.equal(tabContract.stateSelected, "false");

  await page.locator('.tab[data-tab="io"]').focus();
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction(() => document.querySelector('.tab[data-tab="state"]')?.classList.contains("active"));
  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return stage?.dataset.transitionLayoutState === "ready"
      && document.querySelectorAll(".transition-io-cluster").length > 0;
  }, null, { timeout: 60_000 });
  assert.equal(await page.locator('.tab[data-tab="state"]').getAttribute("aria-selected"), "true");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.tab || ""), "state");

  const cluster = page.locator(".transition-io-cluster").first();
  await cluster.focus();
  assert.equal(await cluster.getAttribute("aria-haspopup"), "dialog");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => !document.querySelector(".transition-label-inspector")?.hidden);
  assert.equal(await page.evaluate(() => document.activeElement?.classList.contains("transition-label-inspector-close") || false), true);
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => document.querySelector(".transition-label-inspector")?.hidden === true);
  await page.waitForFunction(() => document.activeElement?.classList.contains("transition-io-cluster"));

  const node = page.locator(".state-node").first();
  await node.focus();
  assert.equal(await node.evaluate(element => element.classList.contains("selected-node")), true);
  const nodeBeforeModal = await node.evaluate(element => ({ left: element.style.left, top: element.style.top }));
  const scaleBeforeModal = await page.locator(".graph-stage").getAttribute("data-viewport-scale");
  const saveRequestsBeforeModal = requests.filter(item => item.method === "POST" && item.url.endsWith("/api/save")).length;

  await page.locator("#glyph-settings").click();
  await page.waitForFunction(() => document.querySelector("#glyph-settings-dialog")?.open === true);
  await page.locator("#glyph-settings-close").focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Control+s");
  await page.keyboard.press("Control+=");
  await page.waitForTimeout(150);
  const nodeDuringModal = await node.evaluate(element => ({ left: element.style.left, top: element.style.top }));
  const scaleDuringModal = await page.locator(".graph-stage").getAttribute("data-viewport-scale");
  const saveRequestsDuringModal = requests.filter(item => item.method === "POST" && item.url.endsWith("/api/save")).length;
  assert.deepEqual(nodeDuringModal, nodeBeforeModal, "arrow key moved a diagram node behind an open modal");
  assert.equal(scaleDuringModal, scaleBeforeModal, "diagram zoom shortcut acted behind an open modal");
  assert.equal(saveRequestsDuringModal, saveRequestsBeforeModal, "save shortcut fired behind an open modal");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => document.querySelector("#glyph-settings-dialog")?.open === false);

  const splitter = page.locator("#splitter");
  const splitterBox = await splitter.boundingBox();
  assert(splitterBox, "splitter is not visible at desktop width");
  const splitX = splitterBox.x + splitterBox.width / 2;
  const splitY = splitterBox.y + Math.min(100, splitterBox.height / 2);
  await page.mouse.move(splitX, splitY);
  await page.mouse.down();
  await page.mouse.move(splitX + 60, splitY, { steps: 5 });
  const editorWidthAfterDrag = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--editor").trim());
  await page.evaluate(() => document.getElementById("splitter")?.dispatchEvent(new PointerEvent("pointercancel", { bubbles: true, pointerId: 999, button: 0 })));
  await page.mouse.move(splitX + 150, splitY, { steps: 5 });
  const editorWidthAfterCancel = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--editor").trim());
  await page.mouse.up();
  assert.equal(editorWidthAfterCancel, editorWidthAfterDrag, "splitter kept resizing after pointer cancellation");

  await page.setViewportSize({ width: 620, height: 760 });
  await page.waitForTimeout(120);
  const narrow = await page.evaluate(() => {
    const main = document.getElementById("main").getBoundingClientRect();
    const editor = document.querySelector(".editor-pane").getBoundingClientRect();
    const viewer = document.querySelector(".viewer").getBoundingClientRect();
    const splitterStyle = getComputedStyle(document.getElementById("splitter"));
    return {
      mainWidth: main.width,
      editorWidth: editor.width,
      editorHeight: editor.height,
      viewerWidth: viewer.width,
      viewerHeight: viewer.height,
      splitterDisplay: splitterStyle.display,
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth,
      settingsVisible: document.getElementById("glyph-settings")?.getBoundingClientRect().width > 0,
      saveVisible: document.getElementById("save")?.getBoundingClientRect().width > 0,
    };
  });
  assert(narrow.editorWidth >= narrow.mainWidth - 2, `narrow editor is not full width: ${JSON.stringify(narrow)}`);
  assert(narrow.viewerWidth >= narrow.mainWidth - 2, `narrow viewer is not full width: ${JSON.stringify(narrow)}`);
  assert(narrow.editorHeight >= 150, `narrow editor became unusably short: ${JSON.stringify(narrow)}`);
  assert(narrow.viewerHeight >= 150, `narrow viewer became unusably short: ${JSON.stringify(narrow)}`);
  assert.equal(narrow.splitterDisplay, "none");
  assert(narrow.scrollWidth <= narrow.innerWidth + 1, `narrow layout overflows horizontally: ${JSON.stringify(narrow)}`);
  assert.equal(narrow.settingsVisible, true);
  assert.equal(narrow.saveVisible, true);

  await page.screenshot({ path: path.join(outputDirectory, "gui-completeness-narrow.png"), fullPage: true });
  const report = {
    tabContract,
    nodeBeforeModal,
    scaleBeforeModal,
    editorWidthAfterDrag,
    editorWidthAfterCancel,
    narrow,
    activePointers: await page.evaluate(() => window.glyphDiagramGuiUxGuard.activePointers()),
  };
  await fs.writeFile(path.join(outputDirectory, "report.json"), `${JSON.stringify(report, null, 2)}\n`);
  assert.equal(report.activePointers, 0, "pointer session leaked after GUI gestures");
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
  await stopProcess(child);
}
