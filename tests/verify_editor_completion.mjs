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
    && window.GlyphEditorLexicalIndex?.version === 2
    && window.GlyphEditorCompletionContext?.version === 1
    && window.GlyphEditorCompletion?.version === 2
    && window.glyphEditorIdentifierHighlight?.version === 2
  ));
  const waitForExactIndex = () => page.waitForFunction(() => {
    const runtime = window.GlyphEditorDocument;
    const snapshot = window.GlyphEditorLexicalIndex?.snapshot?.();
    return snapshot && snapshot.revision === runtime.revision();
  });
  await waitForExactIndex();

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
    window.__glyphCompletionLineMutations = 0;
    window.__glyphCompletionSaveStateEvents = 0;
    const lines = document.getElementById("lines");
    const observer = new MutationObserver(records => {
      window.__glyphCompletionLineMutations += records.length;
    });
    observer.observe(lines, { childList: true, characterData: true, subtree: true });
    window.__glyphCompletionLineObserver = observer;
    document.addEventListener("glyph-save-state-changed", () => {
      window.__glyphCompletionSaveStateEvents += 1;
    });
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
    lineMutations: window.__glyphCompletionLineMutations,
    saveStateEvents: window.__glyphCompletionSaveStateEvents,
  }));
  assert.equal(beforeAccept.expanded, "true");
  assert(beforeAccept.candidates.length <= 8, "completion must be bounded to eight rows");
  assert(beforeAccept.candidates.some(item => item.text === "MotorCommand"));
  assert.equal(beforeAccept.runtimeMetrics.fullLineRecounts, initial.runtimeMetrics.fullLineRecounts, "plain typing must not trigger a full line recount");
  assert.equal(beforeAccept.lineMutations, 0, "plain character typing must not rebuild line-number DOM");
  assert(beforeAccept.saveStateEvents <= 2, `save-state chrome was redundantly refreshed ${beforeAccept.saveStateEvents} times while typing`);
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
    lineMutations: window.__glyphCompletionLineMutations,
  }));
  assert(accepted.source.endsWith("MotorCommand"));
  assert.equal(accepted.popupHidden, true);
  assert.equal(accepted.expanded, "false");
  assert.equal(accepted.completionMetrics.accepts, 1);
  assert.equal(accepted.runtimeMetrics.fullLineRecounts, initial.runtimeMetrics.fullLineRecounts, "completion replacement must not force a full line recount");
  assert.equal(accepted.lineMutations, 0, "completion replacement without newlines must not rebuild line-number DOM");

  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowRight");
  const navigationMetrics = await page.evaluate(() => window.GlyphEditorDocument.metrics());
  assert.equal(navigationMetrics.caretFullScans, accepted.runtimeMetrics.caretFullScans, "adjacent caret navigation must not rescan from the start of the document");
  assert(navigationMetrics.incrementalCaretMoves >= accepted.runtimeMetrics.incrementalCaretMoves, "caret navigation must use the incremental line tracker");

  await page.evaluate(() => window.__glyphCompletionLineObserver?.disconnect());
  const beforeLineEdit = await page.evaluate(() => ({
    count: window.GlyphEditorDocument.lineCount(),
    metrics: window.GlyphEditorDocument.metrics(),
  }));
  await page.keyboard.press("Enter");
  await page.keyboard.press("Backspace");
  const afterLineEdit = await page.evaluate(() => ({
    count: window.GlyphEditorDocument.lineCount(),
    metrics: window.GlyphEditorDocument.metrics(),
  }));
  assert.equal(afterLineEdit.count, beforeLineEdit.count, "newline insert/delete must restore the original line count");
  assert.equal(afterLineEdit.metrics.fullLineRecounts, beforeLineEdit.metrics.fullLineRecounts, "known newline edits must not rescan the document");
  assert.equal(afterLineEdit.metrics.lineSuffixMutations, beforeLineEdit.metrics.lineSuffixMutations + 2, "newline insert/delete must mutate only the line-number suffix");

  const semanticBase = `system ControllerService
  entry cycle
  source read_sensor
  sink write_actuator

resource Buffer[Ready|InFlight|Done]
+Mode=Idle|Running|Stopping|Faulted
+Other=Red|Blue
*Input(value:I)
*System(mode:Mode,command:Other,sequence:U)
*OtherSystem(mode:Other)
*ScalarSystem(mode:I)
>step(state:System,input:Input):System=state
>cycle(system:System,input:Input):System=step(system,input)
>compute(system:System):System=system
>internal_public(system:System):System=system
>resourceful(system:System):System=system
~internal_private(system:System):System=system
ext read_sensor():Input|Error
ext read_backup():Input|Error
!write_actuator(system:System):System|Error
!write_log(system:System):System|Error
`;

  async function installSource(source) {
    await page.evaluate(value => {
      window.__glyphCompletionLineObserver?.disconnect();
      const editor = document.getElementById("editor");
      editor.value = value;
      editor.focus();
      editor.setSelectionRange(editor.value.length, editor.value.length);
    }, source);
    await waitForExactIndex();
  }
  async function typeForContext(source, typed, expectedText, expectedContext) {
    await installSource(source);
    await page.keyboard.type(typed, { delay: 4 });
    await page.waitForFunction(({ text, context }) => {
      const popup = document.getElementById("glyph-completion-popup");
      return popup && !popup.hidden
        && window.GlyphEditorCompletion.context()?.id === context
        && window.GlyphEditorCompletion.candidates().some(item => item.text === text);
    }, { text: expectedText, context: expectedContext });
    return page.evaluate(() => ({
      context: window.GlyphEditorCompletion.context(),
      candidates: window.GlyphEditorCompletion.candidates(),
      snapshotRevision: window.GlyphEditorLexicalIndex.snapshot()?.revision,
      editorRevision: window.GlyphEditorDocument.revision(),
    }));
  }

  const resourceState = await typeForContext(`${semanticBase}\n>probe(buffer:own Buffer[`, "Re", "Ready", "resource-state");
  assert(resourceState.candidates.every(item => item.kind === "State"));
  assert(resourceState.candidates.every(item => item.owners.includes("Buffer")));
  assert(!resourceState.candidates.some(item => item.text === "Red"), "state completion must not leak variants from another owner");
  await page.keyboard.press("Tab");
  await page.waitForFunction(() => document.getElementById("editor").value.endsWith("Buffer[Ready"));

  const typeRows = await typeForContext(`${semanticBase}\n*Probe(value:`, "Sy", "System", "type");
  const systemType = typeRows.candidates.find(item => item.text === "System");
  assert(systemType?.kinds.includes("Type"));

  const builtinRows = await typeForContext(`${semanticBase}\n*Probe(value:`, "St", "String", "type");
  assert.equal(builtinRows.candidates.find(item => item.text === "String")?.kind, "Builtin Type");

  await installSource(`${semanticBase}\n*Probe(value:own `);
  await page.evaluate(() => window.GlyphEditorCompletion.open());
  await page.waitForFunction(() => !document.getElementById("glyph-completion-popup").hidden);
  const qualifiedTypeRows = await page.evaluate(() => ({
    context: window.GlyphEditorCompletion.context(),
    candidates: window.GlyphEditorCompletion.candidates(),
  }));
  assert.equal(qualifiedTypeRows.context.id, "type");
  assert(!qualifiedTypeRows.candidates.some(item => item.kind === "Capability"), "a capability-qualified type must not offer a second capability prefix");

  const entryRows = await typeForContext(`${semanticBase}\nsystem Secondary\n  entry `, "cy", "cycle", "system-entry");
  assert(entryRows.candidates.every(item => item.kinds.includes("Function")));
  assert(!entryRows.candidates.some(item => item.text === "read_sensor"));

  const entryPrivateRows = await typeForContext(`${semanticBase}\nsystem Secondary\n  entry `, "internal_", "internal_public", "system-entry");
  assert(!entryPrivateRows.candidates.some(item => item.text === "internal_private"), "system entry must not offer ~ internal functions");

  const sourceRows = await typeForContext(`${semanticBase}\nsystem Secondary\n  source `, "re", "read_sensor", "system-source");
  assert(sourceRows.candidates.every(item => item.kinds.includes("Source")));
  assert(sourceRows.candidates.some(item => item.text === "read_backup"));

  const sinkRows = await typeForContext(`${semanticBase}\nsystem Secondary\n  sink `, "write_", "write_actuator", "system-sink");
  assert(sinkRows.candidates.every(item => item.kinds.includes("Sink")));
  assert(sinkRows.candidates.some(item => item.text === "write_log"));

  const ownerKinds = await page.evaluate(() => {
    const editor = document.getElementById("editor");
    const row = window.GlyphEditorLexicalIndex.record("mode");
    return {
      ownerKinds: row?.ownerKinds,
      scalarCandidates: window.GlyphEditorLexicalIndex.query("mo", editor.selectionStart, {
        kinds: ["StateField"], owner: "ScalarSystem", limit: 8,
      }),
    };
  });
  assert(ownerKinds.ownerKinds.System.includes("StateField"));
  assert(ownerKinds.ownerKinds.ScalarSystem.includes("Field"));
  assert(!ownerKinds.ownerKinds.ScalarSystem.includes("StateField"));
  assert(!ownerKinds.scalarCandidates.some(item => item.text === "mode"), "StateField kind from one owner must not leak to another owner");

  const machinePrefix = `${semanticBase}\nmachine Controller(state:System,input:Input)\n`;
  const selectRows = await typeForContext(`${machinePrefix}  select=`, "mo", "mode", "machine-select");
  assert(selectRows.candidates.every(item => item.kinds.includes("StateField")));
  assert(!selectRows.candidates.some(item => item.text === "sequence"), "machine select must exclude non-sum fields");
  await page.keyboard.press("Tab");
  await page.waitForFunction(() => document.getElementById("editor").value.endsWith("select=state.mode"));

  const actionRows = await typeForContext(`${machinePrefix}  select=state.mode\n  action=`, "co", "command", "machine-action");
  assert(actionRows.candidates.every(item => item.kinds.includes("StateField")));
  assert(!actionRows.candidates.some(item => item.text === "mode"), "machine action must not offer the select field");
  await page.keyboard.press("Tab");
  await page.waitForFunction(() => document.getElementById("editor").value.endsWith("action=state.command"));

  const initRows = await typeForContext(`${machinePrefix}  select=state.mode\n  init=`, "Sy", "System", "machine-init");
  assert.deepEqual(initRows.candidates.map(item => item.text), ["System"]);

  const nextRows = await typeForContext(`${machinePrefix}  select=state.mode\n  init=System(Idle,Red,0)\n  next=`, "st", "step", "machine-next");
  assert(nextRows.candidates.every(item => item.kinds.includes("Function")));

  const nextPrivateRows = await typeForContext(`${machinePrefix}  select=state.mode\n  init=System(Idle,Red,0)\n  next=`, "internal_", "internal_public", "machine-next");
  assert(!nextPrivateRows.candidates.some(item => item.text === "internal_private"), "machine next must not offer ~ internal functions");

  const successRows = await typeForContext(`${machinePrefix}  select=state.mode\n  success=`, "Ru", "Running", "machine-success");
  assert(successRows.candidates.every(item => item.owners.includes("Mode")));
  assert(!successRows.candidates.some(item => item.text === "Red"));

  const longPadding = Array.from({ length: 180 }, (_, index) => `  # bounded-scope-padding-${index}-${"x".repeat(28)}`).join("\n");
  await installSource(`${machinePrefix}${longPadding}\n  success=Re`);
  const boundedScope = await page.evaluate(() => {
    const editor = document.getElementById("editor");
    const source = editor.value;
    const caret = editor.selectionStart;
    const lineStart = window.GlyphEditorCompletionContext.boundedLineStart(source, caret);
    let left = caret;
    while (left > lineStart && /[A-Za-z0-9_]/.test(source[left - 1])) left -= 1;
    return window.GlyphEditorCompletionContext.classify({
      source,
      caret,
      left,
      right: caret,
      prefix: source.slice(left, caret),
      current: source.slice(left, caret),
      lineStart,
    });
  });
  assert.equal(boundedScope.id, "unsafe-scope", "a truncated machine scope must fail closed instead of falling back to general completion");
  await page.evaluate(() => window.GlyphEditorCompletion.open());
  await page.waitForTimeout(80);
  assert.equal(await page.locator("#glyph-completion-popup").isHidden(), true, "unsafe bounded scope must not show generic candidates");

  const macroSource = `@MAX 100
@limit(x) x
@BLOCK
  MAX
@end
${semanticBase}`;
  await installSource(macroSource);
  const macroKinds = await page.evaluate(() => ({
    MAX: window.GlyphEditorLexicalIndex.record("MAX")?.kinds,
    limit: window.GlyphEditorLexicalIndex.record("limit")?.kinds,
    BLOCK: window.GlyphEditorLexicalIndex.record("BLOCK")?.kinds,
  }));
  assert(macroKinds.MAX.includes("Macro"), "canonical raw macro must be indexed");
  assert(macroKinds.limit.includes("Macro"), "canonical AST macro must be indexed");
  assert(macroKinds.BLOCK.includes("Macro"), "multiline raw macro must be indexed");

  await installSource(`${machinePrefix}  select=m`);
  await page.evaluate(() => window.GlyphEditorCompletion.open());
  await page.waitForFunction(() => window.GlyphEditorCompletion.candidates().some(item => item.text === "mode"));
  const cancelledPending = await page.evaluate(() => {
    const editor = document.getElementById("editor");
    const end = editor.selectionStart;
    window.GlyphEditorDocument.replaceRange(end, end, "o");
    const accepted = window.GlyphEditorCompletion.accept();
    const pendingBeforeEscape = window.GlyphEditorCompletion.metrics().pendingAcceptance;
    const escape = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    editor.dispatchEvent(escape);
    return {
      accepted,
      pendingBeforeEscape,
      pendingAfterEscape: window.GlyphEditorCompletion.metrics().pendingAcceptance,
      defaultPrevented: escape.defaultPrevented,
      source: editor.value,
    };
  });
  assert.equal(cancelledPending.accepted, true, "stale strict acceptance should enter deferred validation");
  assert.equal(cancelledPending.pendingBeforeEscape, true);
  assert.equal(cancelledPending.pendingAfterEscape, false, "Escape must cancel deferred acceptance even while popup is hidden");
  assert.equal(cancelledPending.defaultPrevented, true);
  assert(cancelledPending.source.endsWith("select=mo"));
  await waitForExactIndex();
  await page.waitForTimeout(180);
  assert((await page.locator("#editor").inputValue()).endsWith("select=mo"), "cancelled deferred acceptance must not insert later");

  await installSource(`${semanticBase}\nres`);
  await page.evaluate(() => window.GlyphEditorCompletion.open());
  await page.waitForFunction(() => window.GlyphEditorCompletion.candidates().some(item => item.text === "resource" && item.kind === "Keyword"));
  assert.equal((await page.evaluate(() => window.GlyphEditorCompletion.context()?.id)), "top-level-keyword");
  await page.keyboard.press("Escape");
  await page.evaluate(() => window.GlyphEditorLexicalIndex.refresh());
  await waitForExactIndex();
  await page.waitForTimeout(180);
  assert.equal(await page.locator("#glyph-completion-popup").isHidden(), true, "Escape dismissal must survive an index refresh for the unchanged context");
  await page.keyboard.type("o", { delay: 4 });
  await page.waitForFunction(() => window.GlyphEditorCompletion.candidates().some(item => item.text === "resource"));
  await page.keyboard.press("Tab");
  await page.waitForFunction(() => document.getElementById("editor").value.endsWith("resource"));
  await page.waitForTimeout(180);
  assert.equal(await page.locator("#glyph-completion-popup").isHidden(), true, "accepted completion must not immediately reopen for a longer matching identifier");

  await page.waitForTimeout(250);
  assert.deepEqual(sourceRequests, [], `typing/completion unexpectedly invoked source actions: ${sourceRequests.join(", ")}`);

  await installSource(semanticBase);
  const report = await page.evaluate(() => ({
    revision: window.GlyphEditorDocument.revision(),
    lineCount: window.GlyphEditorDocument.lineCount(),
    lineMutationsDuringTyping: window.__glyphCompletionLineMutations,
    saveStateEventsDuringTyping: window.__glyphCompletionSaveStateEvents,
    runtimeMetrics: window.GlyphEditorDocument.metrics(),
    indexMetrics: window.GlyphEditorLexicalIndex.metrics(),
    completionMetrics: window.GlyphEditorCompletion.metrics(),
    lexicalKinds: {
      Running: window.GlyphEditorLexicalIndex.record("Running")?.kinds,
      mode: window.GlyphEditorLexicalIndex.record("mode")?.kinds,
      step: window.GlyphEditorLexicalIndex.record("step")?.kinds,
    },
  }));
  await page.screenshot({ path: path.join(outputDirectory, "completion.png"), fullPage: true });
  await fs.writeFile(path.join(outputDirectory, "report.json"), `${JSON.stringify(report, null, 2)}\n`);
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
  await stopProcess(child);
}