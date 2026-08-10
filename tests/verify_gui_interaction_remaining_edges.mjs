import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

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
const port = 8905;
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
    && window.glyphDiagramGuiUxContinuity?.version === 1);

  const ioNode = page.locator(".graph-node[data-line]").first();
  assert(await ioNode.count(), "I/O graph fixture has no source-linked graph node");
  assert(Number(await ioNode.getAttribute("data-line")) > 0, "I/O graph node has no valid source line");
  assert.equal(await ioNode.getAttribute("role"), "button");
  assert.equal(await ioNode.getAttribute("tabindex"), "0");
  await ioNode.focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.activeElement?.id === "editor");
  const ioJump = await page.locator("#editor").evaluate(editor => ({
    start: editor.selectionStart,
    end: editor.selectionEnd,
  }));
  assert(ioJump.end > ioJump.start, `I/O keyboard jump did not select a source line: ${JSON.stringify(ioJump)}`);

  const typeCard = page.locator(".type-card[data-line]").first();
  if (await typeCard.count()) {
    assert.equal(await typeCard.getAttribute("role"), "button");
    await typeCard.focus();
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => document.activeElement?.id === "editor");
  }

  await page.locator('.tab[data-tab="state"]').click();
  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return stage?.dataset.transitionLayoutState === "ready" && document.querySelectorAll(".state-node").length > 0;
  }, null, { timeout: 60_000 });

  const canvas = page.locator(".canvas-shell").first();
  const panBefore = await canvas.evaluate(shell => {
    const maxX = Math.max(0, shell.scrollWidth - shell.clientWidth);
    const maxY = Math.max(0, shell.scrollHeight - shell.clientHeight);
    shell.scrollLeft = maxX / 2;
    shell.scrollTop = maxY / 2;
    return { maxX, maxY, left: shell.scrollLeft, top: shell.scrollTop };
  });
  assert(panBefore.maxX > 4 || panBefore.maxY > 4, `diagram canvas has no pannable range: ${JSON.stringify(panBefore)}`);
  await canvas.focus();
  const panKey = panBefore.maxX > 4 ? "ArrowRight" : "ArrowDown";
  await page.keyboard.press(panKey);
  await page.waitForTimeout(60);
  const panAfter = await canvas.evaluate(shell => ({ left: shell.scrollLeft, top: shell.scrollTop }));
  if (panKey === "ArrowRight") assert(panAfter.left > panBefore.left, `ArrowRight did not pan canvas: ${JSON.stringify({ panBefore, panAfter })}`);
  else assert(panAfter.top > panBefore.top, `ArrowDown did not pan canvas: ${JSON.stringify({ panBefore, panAfter })}`);

  let node = page.locator(".state-node").first();
  await node.focus();
  const nodeBefore = await node.evaluate(element => ({
    name: element.querySelector(".state-name")?.textContent?.trim() || "",
    left: element.style.left,
    top: element.style.top,
  }));
  assert(nodeBefore.name, "state node is missing its stable name");
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction(before => {
    const current = [...document.querySelectorAll(".state-node")].find(element => element.querySelector(".state-name")?.textContent?.trim() === before.name);
    return current && (current.style.left !== before.left || current.style.top !== before.top);
  }, nodeBefore, { timeout: 10_000 });
  await page.waitForFunction(name => {
    const active = document.activeElement;
    return active?.classList?.contains("state-node")
      && active.querySelector(".state-name")?.textContent?.trim() === name
      && window.glyphDiagramGuiUxContinuity?.pendingNodeFocus() === "";
  }, nodeBefore.name, { timeout: 10_000 });

  const previewBeforeModal = requests.filter(item => item.method === "POST" && item.url.endsWith("/api/preview")).length;
  await page.locator("#glyph-settings").click();
  await page.waitForFunction(() => document.querySelector("#glyph-settings-dialog")?.open === true);
  await page.locator("#glyph-settings-close").focus();
  await page.keyboard.press("Control+Enter");
  await page.locator("#glyph-language").focus();
  await page.keyboard.press("Control+Enter");
  await page.waitForTimeout(180);
  const previewDuringModal = requests.filter(item => item.method === "POST" && item.url.endsWith("/api/preview")).length;
  assert.equal(previewDuringModal, previewBeforeModal, "compile shortcut fired behind the settings modal");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => document.querySelector("#glyph-settings-dialog")?.open === false);

  const report = {
    ioJump,
    panKey,
    panBefore,
    panAfter,
    stateNode: nodeBefore.name,
    previewRequestsBlocked: previewDuringModal - previewBeforeModal,
  };
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
  await stopProcess(child);
}
