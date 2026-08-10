import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

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
const port = 8935;
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
    const control = { constructors: 0, failuresRemaining: 0, delayMs: 0, injectedFailures: 0 };
    window.__glyphDegradedControl = control;
    class ControlledWorker {
      constructor(url, options) {
        this.url = String(url || "");
        this._native = new NativeWorker(url, options);
        this._onmessage = null;
        this._onerror = null;
        this._onmessageerror = null;
        if (this.url.includes("editor-lexical-worker.js")) control.constructors += 1;
        this._native.onmessage = event => this._onmessage?.(event);
        this._native.onerror = event => this._onerror?.(event);
        this._native.onmessageerror = event => this._onmessageerror?.(event);
      }
      set onmessage(handler) { this._onmessage = handler; }
      get onmessage() { return this._onmessage; }
      set onerror(handler) { this._onerror = handler; }
      get onerror() { return this._onerror; }
      set onmessageerror(handler) { this._onmessageerror = handler; }
      get onmessageerror() { return this._onmessageerror; }
      postMessage(message) {
        const lexical = this.url.includes("editor-lexical-worker.js");
        if (lexical && control.failuresRemaining > 0) {
          control.failuresRemaining -= 1;
          control.injectedFailures += 1;
          setTimeout(() => this._onerror?.({ message: "synthetic permanent lexical failure" }), 0);
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
    && window.glyphEditorExactRevisionGuard?.version === 1
  ));

  const waitForExactIndex = () => page.waitForFunction(() => {
    const snapshot = window.GlyphEditorLexicalIndex?.snapshot?.();
    return snapshot && Number(snapshot.revision) === Number(window.GlyphEditorDocument?.revision?.());
  }, null, { timeout: 10_000 });
  await waitForExactIndex();

  const baseSource = "+Mode=Idle|Faulted\n>MotorCommand():I=0\n";
  await page.evaluate(source => {
    const editor = document.getElementById("editor");
    editor.value = source;
    editor.focus();
    editor.setSelectionRange(editor.value.length, editor.value.length);
  }, baseSource);
  await waitForExactIndex();
  await page.keyboard.type("MotorC", { delay: 4 });
  await page.waitForFunction(() => {
    const popup = document.getElementById("glyph-completion-popup");
    return popup && !popup.hidden
      && window.GlyphEditorCompletion.candidates().some(candidate => candidate.text === "MotorCommand" && candidate.origin === "document");
  }, null, { timeout: 5000 });

  await page.evaluate(() => { window.__glyphDegradedControl.delayMs = 650; });
  await page.keyboard.type("o");
  const staleBeforeAccept = await page.evaluate(() => {
    const editor = document.getElementById("editor");
    const snapshot = window.GlyphEditorLexicalIndex.snapshot?.();
    return {
      source: editor.value,
      popupHidden: document.getElementById("glyph-completion-popup").hidden,
      runtimeRevision: Number(window.GlyphEditorDocument.revision()),
      lexicalRevision: Number(snapshot?.revision ?? -1),
      documentCandidates: window.GlyphEditorCompletion.candidates().filter(candidate => candidate.origin === "document").map(candidate => candidate.text),
      guard: window.glyphEditorExactRevisionGuard.metrics(),
      context: window.GlyphEditorCompletion.context(),
    };
  });
  assert.equal(staleBeforeAccept.popupHidden, true, JSON.stringify(staleBeforeAccept));
  assert.notEqual(staleBeforeAccept.runtimeRevision, staleBeforeAccept.lexicalRevision, JSON.stringify(staleBeforeAccept));
  assert(staleBeforeAccept.documentCandidates.includes("MotorCommand"), JSON.stringify(staleBeforeAccept));
  assert.equal(staleBeforeAccept.context?.strict, false, JSON.stringify(staleBeforeAccept));

  const staleAccept = await page.evaluate(() => {
    const editor = document.getElementById("editor");
    const before = editor.value;
    const blocksBefore = window.glyphEditorExactRevisionGuard.metrics().staleAcceptBlocks;
    const accepted = window.GlyphEditorCompletion.accept();
    return {
      accepted,
      unchanged: editor.value === before,
      popupHidden: document.getElementById("glyph-completion-popup").hidden,
      blocksDelta: window.glyphEditorExactRevisionGuard.metrics().staleAcceptBlocks - blocksBefore,
    };
  });
  assert.equal(staleAccept.accepted, false, JSON.stringify(staleAccept));
  assert.equal(staleAccept.unchanged, true, JSON.stringify(staleAccept));
  assert.equal(staleAccept.popupHidden, true, JSON.stringify(staleAccept));
  assert.equal(staleAccept.blocksDelta, 1, JSON.stringify(staleAccept));
  await waitForExactIndex();
  await page.evaluate(() => { window.__glyphDegradedControl.delayMs = 0; });

  await page.evaluate(source => {
    const editor = document.getElementById("editor");
    editor.value = source;
    editor.focus();
    editor.setSelectionRange(editor.value.length, editor.value.length);
  }, baseSource);
  await waitForExactIndex();

  const beforeExhaustion = await page.evaluate(() => ({
    constructors: window.__glyphDegradedControl.constructors,
    cycles: window.GlyphEditorLexicalIndex.metrics().recoveryCycles,
  }));
  await page.evaluate(() => {
    window.__glyphDegradedControl.failuresRemaining = 20;
    window.GlyphEditorLexicalIndex.invalidate();
  });
  await page.waitForFunction(() => window.GlyphEditorLexicalIndex.metrics().recoveryExhausted === true, null, { timeout: 5000 });
  const exhausted = await page.evaluate(before => ({
    constructorsDelta: window.__glyphDegradedControl.constructors - before.constructors,
    metrics: window.GlyphEditorLexicalIndex.metrics(),
    control: { ...window.__glyphDegradedControl },
  }), beforeExhaustion);
  assert.equal(exhausted.constructorsDelta, 3, JSON.stringify(exhausted));
  assert.equal(exhausted.metrics.recoveryAttempts, 3, JSON.stringify(exhausted));
  assert.equal(exhausted.metrics.recoveryExhausted, true, JSON.stringify(exhausted));

  const exhaustedComposition = await page.evaluate(() => {
    const editor = document.getElementById("editor");
    const runtime = window.GlyphEditorDocument;
    const constructorsBefore = window.__glyphDegradedControl.constructors;
    const source = editor.value;
    const sourceA = `${source}\n# exhausted-a\nExhaustedAlpha`;
    const sourceB = `${source}\n# exhausted-b\nExhaustedBeta`;
    const sourceC = `${source}\n# exhausted-c\nExhaustedFinal`;
    editor.focus();
    editor.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true, data: "x" }));
    runtime.replaceRange(editor.value.length, editor.value.length, "x");
    editor.value = sourceA;
    editor.value = sourceB;
    editor.value = sourceC;
    editor.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true, data: "x" }));
    return { constructorsBefore, finalSource: sourceC };
  });
  await page.waitForTimeout(800);
  const degradedFinal = await page.evaluate(expected => {
    const editor = document.getElementById("editor");
    const lexical = window.GlyphEditorLexicalIndex;
    return {
      sourceMatchesFinal: editor.value === expected.finalSource,
      constructors: window.__glyphDegradedControl.constructors,
      compositionActive: window.GlyphEditorDocument.compositionActive(),
      popupHidden: document.getElementById("glyph-completion-popup").hidden,
      activeIdentifier: editor.dataset.activeIdentifier || "",
      documentCandidateCount: window.GlyphEditorCompletion.candidates().filter(candidate => candidate.origin === "document").length,
      lexical: lexical.metrics(),
      snapshotRevision: Number(lexical.snapshot?.()?.revision ?? -1),
    };
  }, exhaustedComposition);
  assert.equal(degradedFinal.sourceMatchesFinal, true, JSON.stringify(degradedFinal));
  assert.equal(degradedFinal.constructors, exhaustedComposition.constructorsBefore, JSON.stringify(degradedFinal));
  assert.equal(degradedFinal.compositionActive, false, JSON.stringify(degradedFinal));
  assert.equal(degradedFinal.popupHidden, true, JSON.stringify(degradedFinal));
  assert.equal(degradedFinal.activeIdentifier, "", JSON.stringify(degradedFinal));
  assert.equal(degradedFinal.documentCandidateCount, 0, JSON.stringify(degradedFinal));
  assert.equal(degradedFinal.lexical.recoveryExhausted, true, JSON.stringify(degradedFinal));
  assert.equal(degradedFinal.snapshotRevision, -1, JSON.stringify(degradedFinal));

  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify({ staleBeforeAccept, staleAccept, exhausted, degradedFinal }));
} finally {
  await browser.close();
  await stopProcess(child);
}
