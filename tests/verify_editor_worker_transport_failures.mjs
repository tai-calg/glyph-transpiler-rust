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
const port = 8932;
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
      postThrowRemaining: 0,
      messageErrorRemaining: 0,
      invalidMessageRemaining: 0,
    };
    window.__glyphTransportControl = control;

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
        if (lexical && control.postThrowRemaining > 0) {
          control.postThrowRemaining -= 1;
          throw new Error("synthetic lexical postMessage failure");
        }
        if (lexical && control.messageErrorRemaining > 0) {
          control.messageErrorRemaining -= 1;
          setTimeout(() => this._onmessageerror?.({ message: "synthetic lexical messageerror" }), 0);
          return;
        }
        if (lexical && control.invalidMessageRemaining > 0) {
          control.invalidMessageRemaining -= 1;
          setTimeout(() => this._onmessage?.({ data: { type: "invalid" } }), 0);
          return;
        }
        this._native.postMessage(message);
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
  ));

  const waitForExactIndex = () => page.waitForFunction(() => {
    const snapshot = window.GlyphEditorLexicalIndex?.snapshot?.();
    const runtime = window.GlyphEditorDocument;
    return snapshot
      && Number(snapshot.revision) === Number(runtime?.revision?.())
      && !window.GlyphEditorLexicalIndex.metrics().recoveryExhausted;
  }, null, { timeout: 5000 });
  await waitForExactIndex();

  async function exercise(field, expectedMetric) {
    const before = await page.evaluate(() => ({
      constructors: window.__glyphTransportControl.constructors,
      metrics: window.GlyphEditorLexicalIndex.metrics(),
    }));
    await page.evaluate(fieldName => {
      window.__glyphTransportControl[fieldName] = 1;
      window.GlyphEditorLexicalIndex.invalidate();
    }, field);
    await page.waitForFunction(({ beforeState, metric }) => {
      const lexical = window.GlyphEditorLexicalIndex;
      const snapshot = lexical.snapshot?.();
      const metrics = lexical.metrics();
      const runtimeRevision = Number(window.GlyphEditorDocument.revision());
      const metricBefore = Number(beforeState.metrics[metric] || 0);
      return window.__glyphTransportControl.constructors === beforeState.constructors + 1
        && Number(metrics[metric] || 0) === metricBefore + 1
        && metrics.recoveryFailures === 0
        && metrics.recoveryAttempts === 0
        && !metrics.recoveryExhausted
        && snapshot
        && Number(snapshot.revision) === runtimeRevision;
    }, { beforeState: before, metric: expectedMetric }, { timeout: 5000 });
    const after = await page.evaluate(beforeState => ({
      constructorsDelta: window.__glyphTransportControl.constructors - beforeState.constructors,
      metrics: window.GlyphEditorLexicalIndex.metrics(),
      control: { ...window.__glyphTransportControl },
    }), before);
    assert.equal(after.constructorsDelta, 1, JSON.stringify({ field, after }));
    assert.equal(after.metrics.recoveryFailures, 0, JSON.stringify({ field, after }));
    assert.equal(after.metrics.recoveryAttempts, 0, JSON.stringify({ field, after }));
    assert.equal(after.metrics.recoveryExhausted, false, JSON.stringify({ field, after }));
    return after;
  }

  const postThrow = await exercise("postThrowRemaining", "transportFailures");
  const messageError = await exercise("messageErrorRemaining", "transportFailures");
  const invalidMessage = await exercise("invalidMessageRemaining", "invalidMessages");

  assert.equal(postThrow.control.postThrowRemaining, 0, JSON.stringify(postThrow));
  assert.equal(messageError.control.messageErrorRemaining, 0, JSON.stringify(messageError));
  assert.equal(invalidMessage.control.invalidMessageRemaining, 0, JSON.stringify(invalidMessage));
  assert.equal(invalidMessage.metrics.transportFailures, 2, JSON.stringify(invalidMessage));
  assert.equal(invalidMessage.metrics.invalidMessages, 1, JSON.stringify(invalidMessage));
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));

  console.log(JSON.stringify({ postThrow, messageError, invalidMessage }));
} finally {
  await browser.close();
  await stopProcess(child);
}
