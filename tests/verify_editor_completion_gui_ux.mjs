import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const WARM_POPUP_BUDGET_MS = 250;
const LARGE_DOCUMENT_POPUP_BUDGET_MS = 300;

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
const port = 8927;
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
    && window.GlyphEditorLexicalIndex?.version === 2
    && window.GlyphEditorCompletion?.version === 2
    && window.glyphEditorCompletionUxGuard?.version === 1
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
    window.__glyphCompletionUxLatency = {
      lastInputAt: 0,
      lastInputRevision: -1,
      firstVisibleAt: 0,
      firstVisibleRevision: -1,
    };
    editor.addEventListener("input", () => {
      const state = window.__glyphCompletionUxLatency;
      state.lastInputAt = performance.now();
      state.lastInputRevision = runtime.revision();
      state.firstVisibleAt = 0;
      state.firstVisibleRevision = -1;
    });
    const observer = new MutationObserver(() => {
      const state = window.__glyphCompletionUxLatency;
      if (popup.hidden || !popup.querySelector('[role="option"]') || state.firstVisibleAt) return;
      state.firstVisibleAt = performance.now();
      state.firstVisibleRevision = runtime.revision();
    });
    observer.observe(popup, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
    window.__glyphCompletionUxLatencyObserver = observer;
  });

  async function installSource(source) {
    await page.evaluate(value => {
      const editor = document.getElementById("editor");
      editor.value = value;
      editor.focus();
      editor.setSelectionRange(editor.value.length, editor.value.length);
      window.GlyphEditorCompletion.close();
    }, source);
    await waitForExactIndex();
  }

  async function typeAndMeasure(text, expectedCandidate, budgetMs) {
    await page.evaluate(() => {
      const state = window.__glyphCompletionUxLatency;
      state.lastInputAt = 0;
      state.lastInputRevision = -1;
      state.firstVisibleAt = 0;
      state.firstVisibleRevision = -1;
    });
    await page.keyboard.type(text, { delay: 4 });
    await page.waitForFunction(candidate => {
      const popup = document.getElementById("glyph-completion-popup");
      const state = window.__glyphCompletionUxLatency;
      return popup && !popup.hidden
        && state.firstVisibleAt > 0
        && state.firstVisibleRevision === state.lastInputRevision
        && window.GlyphEditorCompletion.candidates().some(item => item.text === candidate);
    }, expectedCandidate, { timeout: 5000 });
    const result = await page.evaluate(() => {
      const state = window.__glyphCompletionUxLatency;
      return {
        latencyMs: state.firstVisibleAt - state.lastInputAt,
        inputRevision: state.lastInputRevision,
        visibleRevision: state.firstVisibleRevision,
        candidates: window.GlyphEditorCompletion.candidates(),
      };
    });
    assert(result.latencyMs >= 0, `negative completion latency: ${JSON.stringify(result)}`);
    assert(result.latencyMs < budgetMs, `completion popup missed ${budgetMs}ms budget: ${JSON.stringify(result)}`);
    return result;
  }

  const editor = page.locator("#editor");
  const originalSource = await editor.inputValue();
  assert(originalSource.includes("MotorCommand"), "fixture must contain MotorCommand");
  await editor.focus();
  await editor.evaluate(element => element.setSelectionRange(element.value.length, element.value.length));

  const warm = await typeAndMeasure("MotorC", "MotorCommand", WARM_POPUP_BUDGET_MS);
  assert.equal(await editor.getAttribute("aria-expanded"), "true");
  assert.equal(await editor.getAttribute("aria-haspopup"), "listbox");
  assert(warm.candidates.length > 0 && warm.candidates.length <= 8, "completion row count must stay bounded");
  await page.screenshot({ path: "build/editor-completion-gui-ux/intellisense-popup.png", fullPage: false });
  assert.equal(
    await page.locator("#glyph-completion-popup [role='option'][tabindex='-1']").count(),
    warm.candidates.length,
    "completion options leaked into the Tab order",
  );
  assert(
    (await page.locator("#glyph-completion-status").textContent())?.includes("completion candidate"),
    "completion live status did not publish candidate count",
  );

  const selectedBefore = await page.evaluate(() => ({
    selected: window.GlyphEditorCompletion.selected(),
    active: document.getElementById("editor").getAttribute("aria-activedescendant"),
  }));
  await page.keyboard.press("ArrowDown");
  const selectedAfter = await page.evaluate(() => ({
    selected: window.GlyphEditorCompletion.selected(),
    active: document.getElementById("editor").getAttribute("aria-activedescendant"),
  }));
  if (warm.candidates.length > 1) {
    assert.notEqual(selectedAfter.selected, selectedBefore.selected, "ArrowDown did not move completion selection");
    assert.notEqual(selectedAfter.active, selectedBefore.active, "aria-activedescendant did not follow selection");
  }

  const motorIndex = warm.candidates.findIndex(item => item.text === "MotorCommand");
  assert(motorIndex >= 0, "MotorCommand disappeared before keyboard acceptance");
  const currentIndex = await page.evaluate(() => window.GlyphEditorCompletion.selected());
  const steps = (motorIndex - currentIndex + warm.candidates.length) % warm.candidates.length;
  for (let index = 0; index < steps; index += 1) await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Tab");
  await page.waitForFunction(() => document.getElementById("editor").value.endsWith("MotorCommand"));
  assert.equal(await page.evaluate(() => document.activeElement?.id), "editor", "Tab completion lost editor focus");
  assert.equal(await editor.getAttribute("aria-expanded"), "false", "Tab completion left popup open");

  await installSource(`${originalSource}\nMotorC`);
  await page.keyboard.press("Backspace");
  await page.keyboard.press("Shift+C");
  await page.waitForFunction(() => !document.getElementById("glyph-completion-popup").hidden);
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => document.getElementById("glyph-completion-popup").hidden);
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(120);
  assert.equal(await editor.getAttribute("aria-expanded"), "false", "Escape dismissal reopened from caret navigation");
  const suppressedDismissal = await page.evaluate(() => window.glyphEditorCompletionUxGuard.metrics());
  assert(suppressedDismissal.suppressAutomaticReopen, "Escape dismissal did not remain sticky");
  await page.keyboard.press("Control+Space");
  await page.waitForFunction(() => !document.getElementById("glyph-completion-popup").hidden);
  assert.equal(
    (await page.evaluate(() => window.glyphEditorCompletionUxGuard.metrics())).suppressAutomaticReopen,
    false,
    "explicit completion did not clear dismissal suppression",
  );
  await page.keyboard.press("Escape");

  const symbolLines = Array.from({ length: 4200 }, (_, index) => `>Symbol${String(index).padStart(4, "0")}():I=0`).join("\n");
  const largeSource = `>TargetCompletion(value:I):I=value\n${symbolLines}\n`;
  await installSource(largeSource);
  const large = await typeAndMeasure("Tar", "TargetCompletion", LARGE_DOCUMENT_POPUP_BUDGET_MS);

  await installSource(largeSource);
  const compactRows = await typeAndMeasure("Sy", "Symbol4199", LARGE_DOCUMENT_POPUP_BUDGET_MS);
  assert.equal(compactRows.candidates.length, 8, "compact fixture must exercise a full completion list");
  await page.setViewportSize({ width: 320, height: 220 });
  await page.waitForTimeout(80);
  const compact = await page.evaluate(() => {
    const rect = document.getElementById("glyph-completion-popup").getBoundingClientRect();
    return {
      left: rect.left,
      top: rect.top,
      right: rect.right,
      bottom: rect.bottom,
      width: rect.width,
      height: rect.height,
      innerWidth,
      innerHeight,
    };
  });
  assert(compact.left >= 7, `popup escaped left viewport edge: ${JSON.stringify(compact)}`);
  assert(compact.top >= 7, `popup escaped top viewport edge: ${JSON.stringify(compact)}`);
  assert(compact.right <= compact.innerWidth - 7, `popup escaped right viewport edge: ${JSON.stringify(compact)}`);
  assert(compact.bottom <= compact.innerHeight - 7, `popup escaped bottom viewport edge: ${JSON.stringify(compact)}`);
  await page.setViewportSize({ width: 1200, height: 820 });
  await page.waitForTimeout(50);

  const pointerTarget = page.locator("#glyph-completion-popup [role='option']").first();
  const pointerText = (await pointerTarget.locator(".glyph-completion-label").textContent())?.trim() || "";
  assert(pointerText, "pointer completion target has no label");
  const box = await pointerTarget.boundingBox();
  assert(box, "pointer completion target has no bounding box");
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForFunction(text => document.getElementById("editor").value.endsWith(text), pointerText);
  assert.equal(await page.evaluate(() => document.activeElement?.id), "editor", "pointer completion lost editor focus");
  await waitForExactIndex();

  const recovery = await page.evaluate(async () => {
    const lexical = window.GlyphEditorLexicalIndex;
    const runtime = window.GlyphEditorDocument;
    const original = { snapshot: lexical.snapshot, metrics: lexical.metrics, invalidate: lexical.invalidate };
    let invalidations = 0;
    let exact = false;
    lexical.snapshot = () => exact ? { revision: runtime.revision() } : null;
    lexical.metrics = () => ({ inFlight: false });
    lexical.invalidate = () => { invalidations += 1; };
    const fail = () => document.dispatchEvent(new CustomEvent("glyph-editor-lexical-index-error", { detail: { message: "synthetic worker failure" } }));
    const succeed = () => document.dispatchEvent(new CustomEvent("glyph-editor-lexical-index-updated", { detail: { exact: true, revision: runtime.revision() } }));
    const waitForInvalidations = async target => {
      const deadline = performance.now() + 1500;
      while (invalidations < target && performance.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 25));
      }
      return invalidations;
    };
    fail();
    const firstCycle = await waitForInvalidations(1);
    exact = true;
    succeed();
    await new Promise(resolve => setTimeout(resolve, 30));
    exact = false;
    fail();
    const secondCycle = await waitForInvalidations(2);
    exact = true;
    succeed();
    lexical.snapshot = original.snapshot;
    lexical.metrics = original.metrics;
    lexical.invalidate = original.invalidate;
    return { firstCycle, secondCycle, metrics: window.glyphEditorCompletionUxGuard.metrics() };
  });
  assert.equal(recovery.firstCycle, 1, `first Worker recovery cycle failed: ${JSON.stringify(recovery)}`);
  assert.equal(recovery.secondCycle, 2, `second independent Worker recovery cycle failed: ${JSON.stringify(recovery)}`);
  assert(recovery.metrics.guardRecoveries >= 2, `Worker recovery metrics incomplete: ${JSON.stringify(recovery)}`);

  assert.deepEqual(sourceRequests, [], `completion unexpectedly hit save/compile endpoints: ${sourceRequests.join(", ")}`);
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify({
    warmPopupLatencyMs: warm.latencyMs,
    largeDocumentPopupLatencyMs: large.latencyMs,
    compactViewport: compact,
    escapeDismissalSuppressed: true,
    keyboardAcceptanceFocusPreserved: true,
    pointerAcceptanceFocusPreserved: true,
    workerRecoveryCycles: recovery,
    completionUxMetrics: await page.evaluate(() => window.glyphEditorCompletionUxGuard.metrics()),
  }));
} finally {
  await browser.close();
  await stopProcess(child);
}
