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

  await page.addInitScript(() => {
    const NativeWorker = window.Worker;
    const control = {
      constructors: 0,
      posts: 0,
      injectedFailures: 0,
      failuresRemaining: 0,
      delayMs: 0,
    };
    window.__glyphWorkerControl = control;

    class ControlledWorker {
      constructor(url, options) {
        this.url = String(url || "");
        this._native = new NativeWorker(url, options);
        this._onmessage = null;
        this._onerror = null;
        if (this.url.includes("editor-lexical-worker.js")) control.constructors += 1;
        this._native.onmessage = event => this._onmessage?.(event);
        this._native.onerror = event => this._onerror?.(event);
      }
      set onmessage(handler) { this._onmessage = handler; }
      get onmessage() { return this._onmessage; }
      set onerror(handler) { this._onerror = handler; }
      get onerror() { return this._onerror; }
      postMessage(message) {
        const lexical = this.url.includes("editor-lexical-worker.js");
        if (lexical) control.posts += 1;
        if (lexical && control.failuresRemaining > 0) {
          control.failuresRemaining -= 1;
          control.injectedFailures += 1;
          setTimeout(() => this._onerror?.({ message: "synthetic lexical Worker failure" }), 0);
          return;
        }
        const deliver = () => this._native.postMessage(message);
        if (lexical && control.delayMs > 0) setTimeout(deliver, control.delayMs);
        else deliver();
      }
      terminate() { return this._native.terminate(); }
    }
    window.Worker = ControlledWorker;
  });

  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.waitForFunction(() => (
    window.GlyphEditorDocument?.version === 1
    && window.GlyphEditorLexicalIndex?.version === 2
    && window.GlyphEditorCompletion?.version === 2
    && window.glyphEditorCompletionUxGuard?.version === 1
    && window.glyphEditorExactRevisionGuard?.version === 1
  ));
  const waitForExactIndex = () => page.waitForFunction(() => {
    const snapshot = window.GlyphEditorLexicalIndex?.snapshot?.();
    return snapshot && Number(snapshot.revision) === Number(window.GlyphEditorDocument?.revision?.());
  }, null, { timeout: 15_000 });
  await waitForExactIndex();

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
      staleVisibleObservations: 0,
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
      if (popup.hidden || !popup.querySelector('[role="option"]') || !snapshot) return;
      const runtimeRevision = Number(runtime.revision());
      const lexicalRevision = Number(snapshot.revision);
      if (runtimeRevision !== lexicalRevision) {
        probe.staleVisibleObservations += 1;
        return;
      }
      if (probe.visibleAt) return;
      probe.visibleAt = performance.now();
      probe.visibleRuntimeRevision = runtimeRevision;
      probe.visibleLexicalRevision = lexicalRevision;
    });
    observer.observe(popup, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
    window.__glyphExactCompletionObserver = observer;
  });

  const editor = page.locator("#editor");
  const originalSource = await editor.inputValue();
  await editor.focus();
  await editor.evaluate(element => element.setSelectionRange(element.value.length, element.value.length));
  const completionMetricsBefore = await page.evaluate(() => window.GlyphEditorCompletion.metrics());
  await page.keyboard.type("MotorC", { delay: 4 });
  await page.waitForFunction(() => {
    const popup = document.getElementById("glyph-completion-popup");
    const probe = window.__glyphExactCompletionProbe;
    return popup && !popup.hidden
      && probe.visibleAt > 0
      && window.GlyphEditorCompletion.candidates().some(item => item.text === "MotorCommand");
  }, null, { timeout: 5000 });

  const publication = await page.evaluate(before => {
    const probe = window.__glyphExactCompletionProbe;
    const guardMetrics = window.glyphEditorCompletionUxGuard.metrics();
    const completionMetrics = window.GlyphEditorCompletion.metrics();
    return {
      ...probe,
      latencyMs: probe.visibleAt - probe.inputAt,
      stalePublicationBlocks: guardMetrics.stalePublicationBlocks,
      staleDocumentQueryBlocks: completionMetrics.staleDocumentQueryBlocks - Number(before.staleDocumentQueryBlocks || 0),
    };
  }, completionMetricsBefore);
  assert.equal(publication.visibleRuntimeRevision, publication.inputRevision, JSON.stringify(publication));
  assert.equal(publication.visibleLexicalRevision, publication.inputRevision, JSON.stringify(publication));
  assert.equal(publication.staleVisibleObservations, 0, JSON.stringify(publication));
  assert(publication.latencyMs >= 0 && publication.latencyMs < POPUP_BUDGET_MS, JSON.stringify(publication));
  assert(publication.staleDocumentQueryBlocks >= 1, `stale document query was not suppressed: ${JSON.stringify(publication)}`);

  // Keep the lexical Worker stale long enough to observe the post-input window directly.
  await page.evaluate(() => { window.__glyphWorkerControl.delayMs = 650; });
  await page.keyboard.type("o");
  const stalePopupWindow = await page.evaluate(() => {
    const popup = document.getElementById("glyph-completion-popup");
    const runtime = window.GlyphEditorDocument;
    const snapshot = window.GlyphEditorLexicalIndex.snapshot?.();
    return {
      popupHidden: popup.hidden,
      runtimeRevision: Number(runtime.revision()),
      lexicalRevision: Number(snapshot?.revision ?? -1),
      activeIdentifier: document.getElementById("editor").dataset.activeIdentifier || "",
      exactGuard: window.glyphEditorExactRevisionGuard.metrics(),
    };
  });
  assert.equal(stalePopupWindow.popupHidden, true, JSON.stringify(stalePopupWindow));
  assert.notEqual(stalePopupWindow.runtimeRevision, stalePopupWindow.lexicalRevision, JSON.stringify(stalePopupWindow));
  assert.equal(stalePopupWindow.activeIdentifier, "", JSON.stringify(stalePopupWindow));
  await waitForExactIndex();
  await page.evaluate(() => { window.__glyphWorkerControl.delayMs = 0; });
  window;

  // Exact identifier highlighting must disappear synchronously on the next edit.
  await page.evaluate(source => {
    const editor = document.getElementById("editor");
    editor.value = source;
    const position = source.indexOf("MotorCommand");
    if (position < 0) throw new Error("MotorCommand missing from exact-revision fixture");
    editor.focus();
    editor.setSelectionRange(position + 2, position + 2);
  }, originalSource);
  await waitForExactIndex();
  await page.evaluate(() => window.glyphEditorIdentifierHighlight.refresh());
  await page.waitForFunction(() => document.getElementById("editor")?.dataset.activeIdentifier === "MotorCommand");
  await page.evaluate(() => { window.__glyphWorkerControl.delayMs = 650; });
  await page.keyboard.type("X");
  const staleHighlightWindow = await page.evaluate(() => {
    const editor = document.getElementById("editor");
    const snapshot = window.GlyphEditorLexicalIndex.snapshot?.();
    return {
      activeIdentifier: editor.dataset.activeIdentifier || "",
      apiIdentifier: window.glyphEditorIdentifierHighlight.identifier(),
      matchCount: window.glyphEditorIdentifierHighlight.matchCount(),
      runtimeRevision: Number(window.GlyphEditorDocument.revision()),
      lexicalRevision: Number(snapshot?.revision ?? -1),
    };
  });
  assert.equal(staleHighlightWindow.activeIdentifier, "", JSON.stringify(staleHighlightWindow));
  assert.equal(staleHighlightWindow.apiIdentifier, "", JSON.stringify(staleHighlightWindow));
  assert.equal(staleHighlightWindow.matchCount, 0, JSON.stringify(staleHighlightWindow));
  assert.notEqual(staleHighlightWindow.runtimeRevision, staleHighlightWindow.lexicalRevision, JSON.stringify(staleHighlightWindow));
  await waitForExactIndex();
  await page.evaluate(() => { window.__glyphWorkerControl.delayMs = 0; });

  // Restore a known valid source before exercising actual Worker.onerror recovery.
  await page.evaluate(source => {
    const editor = document.getElementById("editor");
    editor.value = source;
    editor.focus();
    editor.setSelectionRange(editor.value.length, editor.value.length);
  }, originalSource);
  await waitForExactIndex();

  async function runRecoverableFailureCycle() {
    const before = await page.evaluate(() => ({
      constructors: window.__glyphWorkerControl.constructors,
      cycles: window.GlyphEditorLexicalIndex.metrics().recoveryCycles,
    }));
    await page.evaluate(() => {
      window.__glyphWorkerControl.failuresRemaining = 1;
      window.GlyphEditorLexicalIndex.invalidate();
    });
    await page.waitForFunction(expected => {
      const lexical = window.GlyphEditorLexicalIndex;
      const runtime = window.GlyphEditorDocument;
      const snapshot = lexical.snapshot?.();
      const metrics = lexical.metrics();
      return window.__glyphWorkerControl.constructors >= expected.constructors + 1
        && metrics.recoveryCycles >= expected.cycles + 1
        && metrics.recoveryFailures === 0
        && metrics.recoveryAttempts === 0
        && !metrics.recoveryExhausted
        && snapshot
        && Number(snapshot.revision) === Number(runtime.revision());
    }, before, { timeout: 5000 });
    return page.evaluate(beforeState => ({
      constructorsDelta: window.__glyphWorkerControl.constructors - beforeState.constructors,
      metrics: window.GlyphEditorLexicalIndex.metrics(),
    }), before);
  }

  const recoveryCycle1 = await runRecoverableFailureCycle();
  const recoveryCycle2 = await runRecoverableFailureCycle();
  assert.equal(recoveryCycle1.constructorsDelta, 1, JSON.stringify(recoveryCycle1));
  assert.equal(recoveryCycle2.constructorsDelta, 1, JSON.stringify(recoveryCycle2));
  assert.equal(recoveryCycle2.metrics.recoveryFailures, 0, JSON.stringify(recoveryCycle2));
  assert.equal(recoveryCycle2.metrics.recoveryAttempts, 0, JSON.stringify(recoveryCycle2));

  // Permanent failure must consume exactly the bounded recovery budget, then remain degraded
  // even while further editor input continues to schedule lexical work.
  const permanentBefore = await page.evaluate(() => ({
    constructors: window.__glyphWorkerControl.constructors,
    exhausted: window.GlyphEditorLexicalIndex.metrics().recoveryExhausted,
  }));
  assert.equal(permanentBefore.exhausted, false);
  await page.evaluate(() => {
    window.__glyphWorkerControl.failuresRemaining = 20;
    window.GlyphEditorLexicalIndex.invalidate();
  });
  await page.waitForFunction(() => window.GlyphEditorLexicalIndex.metrics().recoveryExhausted === true, null, { timeout: 5000 });
  const exhausted = await page.evaluate(beforeState => ({
    constructorsDelta: window.__glyphWorkerControl.constructors - beforeState.constructors,
    control: { ...window.__glyphWorkerControl },
    lexical: window.GlyphEditorLexicalIndex.metrics(),
    popupHidden: document.getElementById("glyph-completion-popup").hidden,
    activeIdentifier: document.getElementById("editor").dataset.activeIdentifier || "",
  }), permanentBefore);
  assert.equal(exhausted.constructorsDelta, 3, JSON.stringify(exhausted));
  assert.equal(exhausted.lexical.recoveryAttempts, 3, JSON.stringify(exhausted));
  assert.equal(exhausted.lexical.recoveryExhausted, true, JSON.stringify(exhausted));
  assert.equal(exhausted.popupHidden, true, JSON.stringify(exhausted));
  assert.equal(exhausted.activeIdentifier, "", JSON.stringify(exhausted));

  const constructorsAtExhaustion = exhausted.control.constructors;
  await editor.focus();
  await editor.evaluate(element => element.setSelectionRange(element.value.length, element.value.length));
  await page.keyboard.type("abcdef", { delay: 5 });
  await page.waitForTimeout(700);
  const degradedAfterInput = await page.evaluate(() => ({
    constructors: window.__glyphWorkerControl.constructors,
    lexical: window.GlyphEditorLexicalIndex.metrics(),
    popupHidden: document.getElementById("glyph-completion-popup").hidden,
    activeIdentifier: document.getElementById("editor").dataset.activeIdentifier || "",
  }));
  assert.equal(degradedAfterInput.constructors, constructorsAtExhaustion, JSON.stringify(degradedAfterInput));
  assert.equal(degradedAfterInput.lexical.recoveryExhausted, true, JSON.stringify(degradedAfterInput));
  assert.equal(degradedAfterInput.popupHidden, true, JSON.stringify(degradedAfterInput));
  assert.equal(degradedAfterInput.activeIdentifier, "", JSON.stringify(degradedAfterInput));

  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify({
    publication,
    stalePopupWindow,
    staleHighlightWindow,
    recoveryCycle1,
    recoveryCycle2,
    exhausted,
    degradedAfterInput,
  }));
} finally {
  await browser.close();
  await stopProcess(child);
}
