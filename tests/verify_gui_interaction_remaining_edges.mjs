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
  await waitForServer(url, child, logs);
  const page = await browser.newPage({ viewport: { width: 1200, height: 820 } });
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });
  page.on("request", request => requests.push({ method: request.method(), url: request.url() }));
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready"
    && window.glyphDiagramGuiUxContinuity?.version === 2);

  const editor = page.locator("#editor");
  const originalSource = await editor.inputValue();
  await editor.focus();
  await editor.evaluate(element => element.setSelectionRange(0, 0));
  await page.keyboard.press("Tab");
  await page.waitForFunction(source => document.querySelector("#editor")?.value === `  ${source}`, originalSource);
  assert.equal(await page.evaluate(() => document.activeElement?.id), "editor", "ordinary Tab moved focus out of the source editor");
  await page.keyboard.press("Shift+Tab");
  await page.waitForFunction(source => document.querySelector("#editor")?.value === source, originalSource);
  assert.equal(await page.evaluate(() => document.activeElement?.id), "editor", "Shift+Tab moved focus out of the source editor");

  const firstBreak = originalSource.indexOf("\n");
  const secondBreak = firstBreak >= 0 ? originalSource.indexOf("\n", firstBreak + 1) : -1;
  if (firstBreak >= 0) {
    const selectionEnd = secondBreak >= 0 ? secondBreak : firstBreak;
    await editor.evaluate((element, end) => element.setSelectionRange(0, end), selectionEnd);
    await page.keyboard.press("Tab");
    const indentedBlock = await editor.inputValue();
    assert(indentedBlock.startsWith("  "), "selected-line Tab did not indent the first line");
    if (selectionEnd > firstBreak) assert(indentedBlock.slice(firstBreak + 3).startsWith("  "), "selected-line Tab did not indent the following line");
    await page.keyboard.press("Shift+Tab");
    await page.waitForFunction(source => document.querySelector("#editor")?.value === source, originalSource);
  }

  await page.evaluate(() => {
    const editorElement = document.getElementById("editor");
    window.GlyphEditorDocument.replaceRange(0, 0, "re\n");
    editorElement.setSelectionRange(2, 2);
    window.GlyphEditorCompletion.open();
  });
  await page.waitForFunction(() => document.querySelector("#editor")?.getAttribute("aria-expanded") === "true"
    && window.GlyphEditorCompletion?.candidates?.().some(candidate => candidate.text === "resource"));
  const beforeShiftTabCompletion = await editor.inputValue();
  await page.keyboard.press("Shift+Tab");
  await page.waitForTimeout(60);
  assert.equal(await editor.inputValue(), beforeShiftTabCompletion, "Shift+Tab accepted or modified an autocomplete candidate instead of outdenting");
  assert.equal(await page.evaluate(() => document.activeElement?.id), "editor", "Shift+Tab escaped the editor while completion was open");
  assert.equal(await editor.getAttribute("aria-expanded"), "false", "Shift+Tab left the completion popup open");
  await page.evaluate(() => window.GlyphEditorDocument.replaceRange(0, 3, ""));
  await page.waitForFunction(source => document.querySelector("#editor")?.value === source, originalSource);

  await page.locator('.tab[data-tab="io"]').click();
  await page.waitForFunction(() => document.querySelector('.tab.active')?.dataset.tab === "io"
    && document.querySelectorAll(".graph-node[data-line]").length > 0);

  const ioNode = page.locator(".graph-node[data-line]").first();
  assert(await ioNode.count(), "executable-system fixture has no source-linked I/O graph node");
  const ioLine = Number(await ioNode.getAttribute("data-line"));
  assert(ioLine > 0, "I/O graph node has no valid source line");
  assert.equal(await ioNode.getAttribute("role"), "button");
  assert.equal(await ioNode.getAttribute("tabindex"), "0");
  assert((await ioNode.getAttribute("aria-label"))?.includes(`ソース ${ioLine} 行目`), "I/O jump label is not localized to Japanese");
  await ioNode.focus();
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.activeElement?.id === "editor");
  const ioJump = await page.locator("#editor").evaluate((editorElement, line) => {
    const source = editorElement.value;
    const lines = source.split("\n");
    return {
      start: editorElement.selectionStart,
      end: editorElement.selectionEnd,
      selected: source.slice(editorElement.selectionStart, editorElement.selectionEnd),
      expected: lines[line - 1] ?? "",
    };
  }, ioLine);
  assert.equal(ioJump.selected, ioJump.expected, `I/O keyboard jump selected the wrong source line: ${JSON.stringify(ioJump)}`);

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
    return document.querySelector('.tab.active')?.dataset.tab === "state"
      && stage?.dataset.transitionLayoutState === "ready"
      && document.querySelectorAll(".state-node").length > 0;
  }, null, { timeout: 60_000 });

  const canvas = page.locator(".canvas-shell").first();
  assert.equal(await canvas.getAttribute("aria-label"), "図キャンバス。矢印キーで移動");
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

  const node = page.locator(".state-node").first();
  await node.focus();
  const nodeBefore = await node.evaluate(element => ({
    name: element.querySelector(".state-name")?.textContent?.trim() || "",
    left: element.style.left,
    top: element.style.top,
  }));
  assert(nodeBefore.name, "state node is missing its stable name");
  let stateNodeMoveCount = 0;
  for (let move = 0; move < 3; move += 1) {
    const beforeMove = await page.evaluate(name => {
      const current = [...document.querySelectorAll(".state-node")].find(element => element.querySelector(".state-name")?.textContent?.trim() === name);
      return current ? { left: current.style.left, top: current.style.top } : null;
    }, nodeBefore.name);
    assert(beforeMove, `state node disappeared before keyboard move ${move + 1}`);
    await page.keyboard.press("ArrowRight");
    await page.waitForFunction(({ name, before }) => {
      const current = [...document.querySelectorAll(".state-node")].find(element => element.querySelector(".state-name")?.textContent?.trim() === name);
      return current && (current.style.left !== before.left || current.style.top !== before.top);
    }, { name: nodeBefore.name, before: beforeMove }, { timeout: 10_000 });
    await page.waitForFunction(name => {
      const active = document.activeElement;
      return active?.classList?.contains("state-node")
        && active.querySelector(".state-name")?.textContent?.trim() === name
        && window.glyphDiagramGuiUxContinuity?.pendingNodeFocus() === "";
    }, nodeBefore.name, { timeout: 10_000 });
    stateNodeMoveCount += 1;
  }

  const previewBeforeModal = requests.filter(item => item.method === "POST" && item.url.endsWith("/api/preview")).length;
  await page.locator("#glyph-settings").click();
  await page.waitForFunction(() => document.querySelector("#glyph-settings-dialog")?.open === true);
  await page.locator("#glyph-settings-close").focus();
  for (let index = 0; index < 4; index += 1) {
    await page.keyboard.press("Tab");
    assert(await page.evaluate(() => document.querySelector("#glyph-settings-dialog")?.contains(document.activeElement)), "Tab escaped the modal settings dialog");
  }
  await page.locator("#glyph-settings-close").focus();
  await page.keyboard.press("Control+Enter");
  await page.locator("#glyph-language").selectOption("en");
  await page.waitForFunction(() => document.documentElement.lang === "en"
    && document.querySelector(".canvas-shell")?.getAttribute("aria-label") === "Diagram canvas; use Arrow keys to pan");
  await page.locator("#glyph-language").focus();
  await page.keyboard.press("Control+Enter");
  await page.waitForTimeout(180);
  const previewDuringModal = requests.filter(item => item.method === "POST" && item.url.endsWith("/api/preview")).length;
  assert.equal(previewDuringModal, previewBeforeModal, "compile shortcut fired behind the settings modal");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => document.querySelector("#glyph-settings-dialog")?.open === false
    && document.activeElement?.id === "glyph-settings");

  const report = {
    tabIndentRoundTrip: true,
    shiftTabCompletionBlocked: true,
    ioLine,
    ioJump,
    panKey,
    panBefore,
    panAfter,
    stateNode: nodeBefore.name,
    stateNodeMoveCount,
    previewRequestsBlocked: previewDuringModal - previewBeforeModal,
    modalTabContained: true,
    settingsFocusRestored: true,
  };
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
  await stopProcess(child);
}
