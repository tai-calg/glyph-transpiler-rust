import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const logs = [];
const port = 8914;
const child = spawn("python3", ["glyph.py", "examples/acceptance/motor_safety.glyph"], {
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

async function waitForServer(url) {
  for (let attempt = 0; attempt < 180; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`, { cache: "no-store" });
      if (response.ok && (await response.json()).status === "ready") return;
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Glyph server did not become ready\n${logs.join("")}`);
}

async function stopProcess() {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    new Promise(resolve => setTimeout(resolve, 1500)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

const browser = await chromium.launch({ headless: true });
try {
  const url = `http://127.0.0.1:${port}`;
  await waitForServer(url);
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  const browserErrors = [];
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.waitForFunction(() => (
    window.GlyphEditorDocument?.version === 1
    && window.GlyphEditorLexicalIndex?.version === 2
    && window.glyphEditorIdentifierHighlight?.version === 2
  ));
  const waitExact = () => page.waitForFunction(() => {
    const snapshot = window.GlyphEditorLexicalIndex?.snapshot?.();
    return snapshot && snapshot.revision === window.GlyphEditorDocument.revision();
  });
  await waitExact();

  const original = await page.locator("#editor").inputValue();
  const before = await page.evaluate(() => ({
    revision: window.GlyphEditorDocument.revision(),
    lineCount: window.GlyphEditorDocument.lineCount(),
    metrics: window.GlyphEditorDocument.metrics(),
  }));

  await page.evaluate(() => {
    window.__runtimeSourceReplacementEvents = [];
    window.__runtimeInputEvents = 0;
    document.addEventListener("glyph-editor-source-replaced", event => {
      window.__runtimeSourceReplacementEvents.push({ ...event.detail });
    });
    document.getElementById("editor").addEventListener("input", () => {
      window.__runtimeInputEvents += 1;
    });
    const editor = document.getElementById("editor");
    editor.focus();
    editor.setRangeText("# runtime-range-edit\n", 0, 0, "end");
  });

  const afterRange = await page.evaluate(() => ({
    source: document.getElementById("editor").value,
    revision: window.GlyphEditorDocument.revision(),
    lineCount: window.GlyphEditorDocument.lineCount(),
    metrics: window.GlyphEditorDocument.metrics(),
    events: window.__runtimeSourceReplacementEvents,
    inputEvents: window.__runtimeInputEvents,
    persistence: document.getElementById("glyph-save-state")?.dataset.persistence || "",
  }));
  assert(afterRange.source.startsWith("# runtime-range-edit\n"));
  assert.equal(afterRange.revision, before.revision + 1, "setRangeText must advance revision exactly once");
  assert.equal(afterRange.lineCount, before.lineCount + 1, "setRangeText must update line count");
  assert.equal(afterRange.metrics.programmaticRangeEdits, before.metrics.programmaticRangeEdits + 1);
  assert.equal(afterRange.metrics.incrementalInputs, before.metrics.incrementalInputs, "synthetic input must not double-count runtime revision");
  assert.equal(afterRange.metrics.sourceReplacements, before.metrics.sourceReplacements);
  assert.equal(afterRange.events.length, 1);
  assert.equal(afterRange.events[0].rangeEdit, true);
  assert.equal(afterRange.inputEvents, 1, "setRangeText must still notify existing editor input listeners");
  assert.equal(afterRange.persistence, "unsaved", "programmatic range edit must enter unsaved state");
  await waitExact();

  await page.keyboard.type("x");
  const afterRealInput = await page.evaluate(() => ({
    revision: window.GlyphEditorDocument.revision(),
    metrics: window.GlyphEditorDocument.metrics(),
  }));
  assert.equal(afterRealInput.revision, afterRange.revision + 1, "tracked-input suppression must not leak into the next real keypress");
  assert.equal(afterRealInput.metrics.incrementalInputs, afterRange.metrics.incrementalInputs + 1);

  await page.evaluate(value => {
    const editor = document.getElementById("editor");
    editor.value = value;
    const position = value.indexOf("MotorCommand");
    assert(position >= 0);
    editor.focus();
    editor.setSelectionRange(position + 2, position + 2);
    window.glyphEditorIdentifierHighlight.refresh();
  }, original);
  await waitExact();
  await page.waitForFunction(() => document.getElementById("editor")?.dataset.activeIdentifier === "MotorCommand");
  const highlightBefore = await page.evaluate(() => window.glyphEditorIdentifierHighlight.metrics());
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(80);
  const highlightAfter = await page.evaluate(() => ({
    active: document.getElementById("editor").dataset.activeIdentifier,
    metrics: window.glyphEditorIdentifierHighlight.metrics(),
  }));
  assert.equal(highlightAfter.active, "MotorCommand");
  assert.equal(highlightAfter.metrics.htmlRebuilds, highlightBefore.htmlRebuilds, "moving inside the same identifier must reuse highlight HTML");
  assert(highlightAfter.metrics.htmlReuses > highlightBefore.htmlReuses, "same-identifier caret motion must hit the highlight cache");

  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify({
    rangeRevisionDelta: afterRange.revision - before.revision,
    programmaticRangeEditDelta: afterRange.metrics.programmaticRangeEdits - before.metrics.programmaticRangeEdits,
    realInputRevisionDelta: afterRealInput.revision - afterRange.revision,
    highlightRebuildDelta: highlightAfter.metrics.htmlRebuilds - highlightBefore.htmlRebuilds,
    highlightReuseDelta: highlightAfter.metrics.htmlReuses - highlightBefore.htmlReuses,
  }));
} finally {
  await browser.close();
  await stopProcess();
}