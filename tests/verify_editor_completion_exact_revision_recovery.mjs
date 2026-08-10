import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const POPUP_BUDGET_MS = 250;

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
const port = 8931;
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
  const page = await browser.newPage({ viewport: { width: 1200, height: 820 } });
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });

  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.waitForFunction(() => (
    window.GlyphEditorDocument?.version === 1
    && window.GlyphEditorLexicalIndex?.version === 2
    && window.GlyphEditorCompletion?.version === 2
    && window.glyphEditorCompletionUxGuard?.version === 1
  ));
  await page.waitForFunction(() => {
    const snapshot = window.GlyphEditorLexicalIndex?.snapshot?.();
    return snapshot && Number(snapshot.revision) === Number(window.GlyphEditorDocument?.revision?.());
  });

  await page.evaluate(() => {
    const editor = document.getElementById("editor");
    const popup = document.getElementById("glyph-completion-popup");
    const runtime = window.GlyphEditorDocument;
    const lexical = window.GlyphEditorLexicalIndex;
    window.__glyphExactCompletionProbe = {
      inputAt: 0,
      inputRevision: -1,
      visibleAt: 0,
      visibleRuntimeRevision: -1,
      visibleLexicalRevision: -1,
    };
    editor.addEventListener("input", () => {
      const probe = window.__glyphExactCompletionProbe;
      probe.inputAt = performance.now();
      probe.inputRevision = runtime.revision();
      probe.visibleAt = 0;
      probe.visibleRuntimeRevision = -1;
      probe.visibleLexicalRevision = -1;
    });
    const observer = new MutationObserver(() => {
      const probe = window.__glyphExactCompletionProbe;
      const snapshot = lexical.snapshot?.();
      if (popup.hidden || !popup.querySelector('[role="option"]') || !snapshot || probe.visibleAt) return;
      const runtimeRevision = Number(runtime.revision());
      const lexicalRevision = Number(snapshot.revision);
      if (runtimeRevision !== lexicalRevision) return;
      probe.visibleAt = performance.now();
      probe.visibleRuntimeRevision = runtimeRevision;
      probe.visibleLexicalRevision = lexicalRevision;
    });
    observer.observe(popup, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
    window.__glyphExactCompletionObserver = observer;
  });

  const editor = page.locator("#editor");
  await editor.focus();
  await editor.evaluate(element => element.setSelectionRange(element.value.length, element.value.length));
  await page.keyboard.type("MotorC", { delay: 4 });
  await page.waitForFunction(() => {
    const popup = document.getElementById("glyph-completion-popup");
    const probe = window.__glyphExactCompletionProbe;
    return popup && !popup.hidden
      && probe.visibleAt > 0
      && window.GlyphEditorCompletion.candidates().some(item => item.text === "MotorCommand");
  }, null, { timeout: 5000 });

  const publication = await page.evaluate(() => {
    const probe = window.__glyphExactCompletionProbe;
    const metrics = window.glyphEditorCompletionUxGuard.metrics();
    return {
      ...probe,
      latencyMs: probe.visibleAt - probe.inputAt,
      stalePublicationBlocks: metrics.stalePublicationBlocks,
    };
  });
  assert.equal(publication.visibleRuntimeRevision, publication.inputRevision, JSON.stringify(publication));
  assert.equal(publication.visibleLexicalRevision, publication.inputRevision, JSON.stringify(publication));
  assert(publication.latencyMs >= 0 && publication.latencyMs < POPUP_BUDGET_MS, JSON.stringify(publication));
  assert(publication.stalePublicationBlocks >= 1, `stale publication was not suppressed: ${JSON.stringify(publication)}`);

  await page.keyboard.press("Escape");
  await page.waitForFunction(() => document.getElementById("glyph-completion-popup").hidden);

  const recovery = await page.evaluate(async () => {
    const lexical = window.GlyphEditorLexicalIndex;
    const runtime = window.GlyphEditorDocument;
    const original = { snapshot: lexical.snapshot, metrics: lexical.metrics, invalidate: lexical.invalidate };
    let invalidations = 0;
    let exact = false;
    lexical.snapshot = () => exact ? { revision: runtime.revision() } : null;
    lexical.metrics = () => ({ inFlight: false });
    lexical.invalidate = () => { invalidations += 1; };
    const fail = () => document.dispatchEvent(new CustomEvent("glyph-editor-lexical-index-error", { detail: { message: "synthetic repeated worker failure" } }));
    const succeed = () => document.dispatchEvent(new CustomEvent("glyph-editor-lexical-index-updated", { detail: { exact: true, revision: runtime.revision() } }));
    const waitForInvalidations = async target => {
      const deadline = performance.now() + 1800;
      while (invalidations < target && performance.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 25));
      }
      return invalidations;
    };

    fail();
    const afterFirstFailure = await waitForInvalidations(1);
    fail();
    const afterSecondFailure = await waitForInvalidations(2);
    exact = true;
    succeed();
    await new Promise(resolve => setTimeout(resolve, 40));
    const metrics = window.glyphEditorCompletionUxGuard.metrics();

    lexical.snapshot = original.snapshot;
    lexical.metrics = original.metrics;
    lexical.invalidate = original.invalidate;
    return { afterFirstFailure, afterSecondFailure, metrics };
  });

  assert.equal(recovery.afterFirstFailure, 1, JSON.stringify(recovery));
  assert.equal(recovery.afterSecondFailure, 2, JSON.stringify(recovery));
  assert.equal(recovery.metrics.recoveryFailures, 0, JSON.stringify(recovery));
  assert.equal(recovery.metrics.recoveryAttempts, 0, JSON.stringify(recovery));
  assert.equal(recovery.metrics.recoveryExhausted, 0, JSON.stringify(recovery));
  assert(recovery.metrics.guardRecoveries >= 2, JSON.stringify(recovery));
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));

  console.log(JSON.stringify({ publication, recovery }));
} finally {
  await browser.close();
  await stopProcess(child);
}
