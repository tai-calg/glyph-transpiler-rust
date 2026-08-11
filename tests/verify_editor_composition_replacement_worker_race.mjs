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
const port = 8933;
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
      delayedOldDeliveries: 0,
      injectedFailures: 0,
      armRace: false,
    };
    window.__glyphCompositionRaceControl = control;

    class ControlledWorker {
      constructor(url, options) {
        this.url = String(url || "");
        this._native = new NativeWorker(url, options);
        this._onmessage = null;
        this._onerror = null;
        this._onmessageerror = null;
        this._terminated = false;
        this._raceThisWorker = false;
        if (this.url.includes("editor-lexical-worker.js")) control.constructors += 1;
        this._native.onmessage = event => {
          if (this._raceThisWorker) {
            this._raceThisWorker = false;
            control.delayedOldDeliveries += 1;
            setTimeout(() => this._onmessage?.(event), 500);
            return;
          }
          this._onmessage?.(event);
        };
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
        if (lexical) control.posts += 1;
        if (lexical && control.armRace) {
          control.armRace = false;
          this._raceThisWorker = true;
          this._native.postMessage(message);
          setTimeout(() => {
            control.injectedFailures += 1;
            this._onerror?.({ message: "synthetic failure before delayed old response" });
          }, 60);
          return;
        }
        this._native.postMessage(message);
      }
      terminate() {
        this._terminated = true;
        return this._native.terminate();
      }
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

  const before = await page.evaluate(() => ({
    revision: window.GlyphEditorDocument.revision(),
    constructors: window.__glyphCompositionRaceControl.constructors,
    recoveryCycles: window.GlyphEditorLexicalIndex.metrics().recoveryCycles,
  }));

  const result = await page.evaluate(async () => {
    const editor = document.getElementById("editor");
    const runtime = window.GlyphEditorDocument;
    const lexical = window.GlyphEditorLexicalIndex;
    const completion = window.GlyphEditorCompletion;
    const popup = document.getElementById("glyph-completion-popup");
    const source = editor.value;
    const sourceA = `${source}\n# race-a\nRaceAlphaSymbol`;
    const sourceB = `${source}\n# race-b\nRaceBetaSymbol`;
    const sourceC = `${source}\n# race-c\nRaceFinalSymbol`;
    const observations = [];
    const observe = label => {
      const snapshot = lexical.snapshot?.();
      observations.push({
        label,
        revision: Number(runtime.revision()),
        lexicalRevision: Number(snapshot?.revision ?? -1),
        compositionActive: runtime.compositionActive(),
        popupHidden: popup.hidden,
        activeIdentifier: editor.dataset.activeIdentifier || "",
        candidates: completion.candidates().map(item => ({ text: item.text, origin: item.origin })),
      });
    };

    editor.focus();
    editor.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true, data: "x" }));
    runtime.replaceRange(editor.value.length, editor.value.length, "x");
    observe("composition-input");

    window.__glyphCompositionRaceControl.armRace = true;
    editor.value = sourceA;
    editor.value = sourceB;
    editor.value = sourceC;
    observe("rapid-replacements");

    editor.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true, data: "x" }));
    observe("composition-end");

    return { observations, finalSource: sourceC };
  });

  for (const observation of result.observations) {
    assert.equal(observation.popupHidden, true, JSON.stringify(observation));
    assert.equal(observation.activeIdentifier, "", JSON.stringify(observation));
    assert.equal(
      observation.candidates.some(candidate => candidate.origin === "document"),
      false,
      `document candidate leaked while state was stale/composing: ${JSON.stringify(observation)}`,
    );
  }

  await page.waitForFunction(expected => {
    const control = window.__glyphCompositionRaceControl;
    const lexical = window.GlyphEditorLexicalIndex;
    const runtime = window.GlyphEditorDocument;
    const snapshot = lexical.snapshot?.();
    const metrics = lexical.metrics();
    return control.constructors >= expected.constructors + 1
      && control.injectedFailures === 1
      && control.delayedOldDeliveries === 1
      && metrics.recoveryCycles >= expected.recoveryCycles + 1
      && metrics.recoveryFailures === 0
      && metrics.recoveryAttempts === 0
      && !metrics.recoveryExhausted
      && snapshot
      && Number(snapshot.revision) === Number(runtime.revision());
  }, before, { timeout: 10_000 });

  await page.waitForTimeout(650);
  const finalState = await page.evaluate(finalSource => {
    const editor = document.getElementById("editor");
    const lexical = window.GlyphEditorLexicalIndex;
    const runtime = window.GlyphEditorDocument;
    const snapshot = lexical.snapshot?.();
    return {
      sourceMatchesFinal: editor.value === finalSource,
      runtimeRevision: Number(runtime.revision()),
      lexicalRevision: Number(snapshot?.revision ?? -1),
      compositionActive: runtime.compositionActive(),
      popupHidden: document.getElementById("glyph-completion-popup").hidden,
      activeIdentifier: editor.dataset.activeIdentifier || "",
      alpha: lexical.record("RaceAlphaSymbol"),
      beta: lexical.record("RaceBetaSymbol"),
      final: lexical.record("RaceFinalSymbol"),
      metrics: lexical.metrics(),
      exactGuard: window.glyphEditorExactRevisionGuard.metrics(),
      control: { ...window.__glyphCompositionRaceControl },
    };
  }, result.finalSource);

  assert.equal(finalState.sourceMatchesFinal, true, JSON.stringify(finalState));
  assert.equal(finalState.compositionActive, false, JSON.stringify(finalState));
  assert.equal(finalState.runtimeRevision, finalState.lexicalRevision, JSON.stringify(finalState));
  assert.equal(finalState.alpha, null, JSON.stringify(finalState));
  assert.equal(finalState.beta, null, JSON.stringify(finalState));
  assert(finalState.final, JSON.stringify(finalState));
  assert.equal(finalState.metrics.recoveryFailures, 0, JSON.stringify(finalState));
  assert.equal(finalState.metrics.recoveryAttempts, 0, JSON.stringify(finalState));
  assert.equal(finalState.metrics.recoveryExhausted, false, JSON.stringify(finalState));
  assert.equal(finalState.control.constructors, before.constructors + 1, JSON.stringify(finalState));
  assert.equal(finalState.control.injectedFailures, 1, JSON.stringify(finalState));
  assert.equal(finalState.control.delayedOldDeliveries, 1, JSON.stringify(finalState));
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));

  console.log(JSON.stringify({ before, observations: result.observations, finalState }));
} finally {
  await browser.close();
  await stopProcess(child);
}
