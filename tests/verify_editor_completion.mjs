import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/editor-completion");
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

const logs = [];
const browserErrors = [];
const sourceRequests = [];
const port = 8913;
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

const browser = await chromium.launch({ headless: true });
try {
  const url = `http://127.0.0.1:${port}`;
  await waitForServer(url, child, logs);
  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });
  page.on("request", request => {
    const target = new URL(request.url());
    if (request.method() === "POST" && ["/api/save", "/api/rebuild", "/api/preview"].includes(target.pathname)) {
      sourceRequests.push(`${request.method()} ${target.pathname}`);
    }
  });

  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.waitForFunction(() => (
    window.GlyphEditorDocument?.version === 1
    && window.GlyphEditorLexicalIndex?.version === 1
    && window.GlyphEditorCompletion?.version === 1
    && window.glyphEditorIdentifierHighlight?.version === 2
  ));
  await page.waitForFunction(() => {
    const runtime = window.GlyphEditorDocument;
    const snapshot = window.GlyphEditorLexicalIndex?.snapshot?.();
    return snapshot && snapshot.revision === runtime.revision();
  });

  const initial = await page.evaluate(() => ({
    source: document.getElementById("editor").value,
    revision: window.GlyphEditorDocument.revision(),
    lineCount: window.GlyphEditorDocument.lineCount(),
    runtimeMetrics: window.GlyphEditorDocument.metrics(),
    indexMetrics: window.GlyphEditorLexicalIndex.metrics(),
  }));
  assert(initial.source.includes("MotorCommand"), "test source must contain MotorCommand");

  await page.evaluate(() => {
    const editor = document.getElementById("editor");
    editor.focus();
    editor.setSelectionRange(editor.value.length, editor.value.length);
  });
  await page.keyboard.type("MotorC", { delay: 8 });

  await page.waitForFunction(() => {
    const popup = document.getElementById("glyph-completion-popup");
    return popup && !popup.hidden
      && window.GlyphEditorCompletion.candidates().some(item => item.text === "MotorCommand");
  });

  const beforeAccept = await page.evaluate(() => ({
    candidates: window.GlyphEditorCompletion.candidates(),
    revision: window.GlyphEditorDocument.revision(),
    runtimeMetrics: window.GlyphEditorDocument.metrics(),
    indexMetrics: window.GlyphEditorLexicalIndex.metrics(),
    expanded: document.getElementById("editor").getAttribute("aria-expanded"),
  }));
  assert.equal(beforeAccept.expanded, "true");
  assert(beforeAccept.candidates.length <= 8, "completion must be bounded to eight rows");
  assert(beforeAccept.candidates.some(item => item.text === "MotorCommand"));
  assert.equal(
    beforeAccept.runtimeMetrics.fullLineRecounts,
    initial.runtimeMetrics.fullLineRecounts,
    "plain typing must not trigger a full line recount",
  );
  assert(beforeAccept.indexMetrics.maxPendingDepth <= 1, "worker pending queue must stay bounded");

  const motorCommandIndex = beforeAccept.candidates.findIndex(item => item.text === "MotorCommand");
  for (let index = 0; index < motorCommandIndex; index += 1) await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Tab");

  await page.waitForFunction(() => document.getElementById("editor").value.endsWith("MotorCommand"));
  const accepted = await page.evaluate(() => ({
    source: document.getElementById("editor").value,
    popupHidden: document.getElementById("glyph-completion-popup").hidden,
    expanded: document.getElementById("editor").getAttribute("aria-expanded"),
    completionMetrics: window.GlyphEditorCompletion.metrics(),
    runtimeMetrics: window.GlyphEditorDocument.metrics(),
  }));
  assert(accepted.source.endsWith("MotorCommand"));
  assert.equal(accepted.popupHidden, true);
  assert.equal(accepted.expanded, "false");
  assert.equal(accepted.completionMetrics.accepts, 1);
  assert.equal(
    accepted.runtimeMetrics.fullLineRecounts,
    initial.runtimeMetrics.fullLineRecounts,
    "completion replacement must not force a full line recount",
  );

  await page.waitForTimeout(250);
  assert.deepEqual(sourceRequests, [], `typing/completion unexpectedly invoked source actions: ${sourceRequests.join(", ")}`);

  const replacement = await page.evaluate(() => {
    const editor = document.getElementById("editor");
    const source = editor.value;
    editor.value = source.replace(/MotorCommand/g, "CommandAfterReplace");
    return {
      revision: window.GlyphEditorDocument.revision(),
      snapshot: window.GlyphEditorLexicalIndex.snapshot()?.revision ?? -1,
    };
  });
  assert(replacement.revision > beforeAccept.revision);
  assert.notEqual(replacement.snapshot, replacement.revision, "full source replacement must invalidate the old index immediately");
  await page.waitForFunction(() => {
    const runtime = window.GlyphEditorDocument;
    const index = window.GlyphEditorLexicalIndex;
    const snapshot = index.snapshot();
    return snapshot
      && snapshot.revision === runtime.revision()
      && index.record("CommandAfterReplace")?.codeCount > 0
      && !index.record("MotorCommand");
  });

  await page.screenshot({ path: path.join(outputDirectory, "completion.png"), fullPage: true });
  const report = await page.evaluate(() => ({
    revision: window.GlyphEditorDocument.revision(),
    lineCount: window.GlyphEditorDocument.lineCount(),
    runtimeMetrics: window.GlyphEditorDocument.metrics(),
    indexMetrics: window.GlyphEditorLexicalIndex.metrics(),
    completionMetrics: window.GlyphEditorCompletion.metrics(),
  }));
  await fs.writeFile(path.join(outputDirectory, "report.json"), `${JSON.stringify(report, null, 2)}\n`);
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
  await stopProcess(child);
}
