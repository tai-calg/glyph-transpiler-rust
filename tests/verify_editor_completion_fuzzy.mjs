import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const FUZZY_POPUP_BUDGET_MS = 180;
const LARGE_FUZZY_POPUP_BUDGET_MS = 220;

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
const port = 8934;
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
    && typeof window.GlyphEditorLexicalIndex?.matchText === "function"
    && window.GlyphEditorCompletion?.version === 2
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
    window.__glyphFuzzyLatency = { inputAt: 0, inputRevision: -1, visibleAt: 0, visibleRevision: -1 };
    editor.addEventListener("input", () => {
      const state = window.__glyphFuzzyLatency;
      state.inputAt = performance.now();
      state.inputRevision = runtime.revision();
      state.visibleAt = 0;
      state.visibleRevision = -1;
    });
    new MutationObserver(() => {
      const state = window.__glyphFuzzyLatency;
      if (popup.hidden || !popup.querySelector('[role="option"]') || state.visibleAt) return;
      const snapshot = window.GlyphEditorLexicalIndex.snapshot?.();
      if (!snapshot || Number(snapshot.revision) !== Number(runtime.revision())) return;
      state.visibleAt = performance.now();
      state.visibleRevision = runtime.revision();
    }).observe(popup, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
  });

  const machineBase = `+Mode=Idle|Running|Stopping|Faulted
+Other=Falter|Fallback
*Input(value:I)
*System(mode:Mode)
>step(state:System,input:Input):System=state
machine Controller(state:System,input:Input)
  select=state.mode
  init=System(Idle)
  next=step
  success=`;

  async function installSource(source) {
    await page.evaluate(value => {
      const editor = document.getElementById("editor");
      editor.value = value;
      editor.focus();
      editor.setSelectionRange(editor.value.length, editor.value.length);
      window.GlyphEditorCompletion.close();
      const state = window.__glyphFuzzyLatency;
      state.inputAt = 0;
      state.inputRevision = -1;
      state.visibleAt = 0;
      state.visibleRevision = -1;
    }, source);
    await waitForExactIndex();
  }

  async function typeAndFind(source, typed, expected, budgetMs = FUZZY_POPUP_BUDGET_MS) {
    await installSource(source);
    await page.keyboard.type(typed, { delay: 3 });
    await page.waitForFunction(text => {
      const popup = document.getElementById("glyph-completion-popup");
      const latency = window.__glyphFuzzyLatency;
      return popup && !popup.hidden
        && latency.visibleAt > 0
        && latency.visibleRevision === latency.inputRevision
        && window.GlyphEditorCompletion.candidates().some(candidate => candidate.text === text);
    }, expected, { timeout: 5000 });
    const state = await page.evaluate(text => {
      const latency = window.__glyphFuzzyLatency;
      const candidates = window.GlyphEditorCompletion.candidates();
      return {
        latencyMs: latency.visibleAt - latency.inputAt,
        candidate: candidates.find(item => item.text === text),
        candidates,
        context: window.GlyphEditorCompletion.context(),
        lexicalMetrics: window.GlyphEditorLexicalIndex.metrics(),
      };
    }, expected);
    assert(state.latencyMs >= 0 && state.latencyMs < budgetMs, JSON.stringify({ typed, expected, state }));
    assert(state.candidate, JSON.stringify({ typed, expected, state }));
    return state;
  }

  const typoCases = [
    { typed: "Fal", mode: "single internal omission", expectedKind: "fuzzy" },
    { typed: "Flted", mode: "multiple omissions", expectedKind: "fuzzy" },
    { typed: "Fauxt", mode: "substitution", expectedKind: "fuzzy" },
    { typed: "Fauult", mode: "extra character", expectedKind: "fuzzy" },
    { typed: "Fual", mode: "adjacent transposition", expectedKind: "fuzzy" },
    { typed: "fal", mode: "case plus omission", expectedKind: "fuzzy" },
    { typed: "Ftd", mode: "sparse non-contiguous subsequence", expectedKind: "subsequence" },
  ];
  const typoResults = [];
  for (const testCase of typoCases) {
    const state = await typeAndFind(machineBase, testCase.typed, "Faulted");
    assert.equal(state.context?.id, "machine-success", JSON.stringify({ testCase, state }));
    assert.equal(state.candidate.origin, "document", JSON.stringify({ testCase, state }));
    assert.equal(state.candidate.matchKind, testCase.expectedKind, JSON.stringify({ testCase, state }));
    assert.equal(state.candidates.some(candidate => candidate.text === "Falter"), false, JSON.stringify({ testCase, state }));
    assert.equal(state.candidates.some(candidate => candidate.text === "Fallback"), false, JSON.stringify({ testCase, state }));
    if (testCase.expectedKind === "fuzzy") assert(Number(state.candidate.matchEdits || 0) <= 3, JSON.stringify({ testCase, state }));
    typoResults.push({ ...testCase, latencyMs: state.latencyMs, candidate: state.candidate });
  }

  const strictOwner = await typeAndFind(machineBase, "Fal", "Faulted");
  assert.equal(strictOwner.context?.owner, "Mode", JSON.stringify(strictOwner));
  assert.equal(strictOwner.context?.strict, true, JSON.stringify(strictOwner));
  assert.equal(strictOwner.candidates.some(candidate => candidate.text === "Falter" || candidate.text === "Fallback"), false, JSON.stringify(strictOwner));

  const acceptState = await typeAndFind(machineBase, "Ftd", "Faulted");
  const faultedIndex = acceptState.candidates.findIndex(candidate => candidate.text === "Faulted");
  assert(faultedIndex >= 0);
  const selected = await page.evaluate(() => window.GlyphEditorCompletion.selected());
  const steps = (faultedIndex - selected + acceptState.candidates.length) % acceptState.candidates.length;
  for (let index = 0; index < steps; index += 1) await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Tab");
  await page.waitForFunction(() => document.getElementById("editor").value.endsWith("success=Faulted"));

  const keyword = await typeAndFind(`${machineBase}\n`, "sysem", "system");
  assert.equal(keyword.candidate.origin, "static", JSON.stringify(keyword));
  assert.equal(keyword.candidate.matchKind, "fuzzy", JSON.stringify(keyword));

  const directMatches = await page.evaluate(() => {
    const match = window.GlyphEditorLexicalIndex.matchText;
    return {
      exact: match("Fau", "Faulted"),
      omission: match("Fal", "Faulted"),
      multipleOmissions: match("Flted", "Faulted"),
      substitution: match("Fauxt", "Faulted"),
      insertion: match("Fauult", "Faulted"),
      transposition: match("Fual", "Faulted"),
      sparse: match("Ftd", "Faulted"),
      camel: match("MC", "MotorCommand"),
      repeatedStart: match("MC", "MegaMotorCommand"),
      unrelated: match("zzz", "Faulted"),
    };
  });
  assert.equal(directMatches.exact?.kind, "prefix", JSON.stringify(directMatches));
  for (const key of ["omission", "multipleOmissions", "substitution", "insertion", "transposition"]) {
    assert.equal(directMatches[key]?.kind, "fuzzy", `${key}: ${JSON.stringify(directMatches)}`);
  }
  assert.equal(directMatches.sparse?.kind, "subsequence", JSON.stringify(directMatches));
  assert.equal(directMatches.camel?.kind, "subsequence", JSON.stringify(directMatches));
  assert.equal(directMatches.repeatedStart?.kind, "subsequence", JSON.stringify(directMatches));
  assert.equal(directMatches.unrelated, null, JSON.stringify(directMatches));

  const symbolLines = Array.from({ length: 4200 }, (_, index) => `>Symbol${String(index).padStart(4, "0")}():I=0`).join("\n");
  const largeSource = `${symbolLines}\n`;
  const largeFuzzy = await typeAndFind(largeSource, "Smbol4199", "Symbol4199", LARGE_FUZZY_POPUP_BUDGET_MS);
  assert.equal(largeFuzzy.candidate.matchKind, "fuzzy", JSON.stringify(largeFuzzy));
  assert(largeFuzzy.lexicalMetrics.fuzzyRowsScanned > 0, JSON.stringify(largeFuzzy));

  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify({
    typoResults,
    strictOwner: { context: strictOwner.context, candidates: strictOwner.candidates.map(candidate => candidate.text) },
    fuzzyAcceptance: true,
    staticKeywordFuzzy: { latencyMs: keyword.latencyMs, candidate: keyword.candidate },
    directMatches,
    largeDocumentFuzzyLatencyMs: largeFuzzy.latencyMs,
    largeDocumentCandidate: largeFuzzy.candidate,
    lexicalMetrics: largeFuzzy.lexicalMetrics,
  }));
} finally {
  await browser.close();
  await stopProcess(child);
}
