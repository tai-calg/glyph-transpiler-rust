import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const source = "examples/acceptance/door_execution_contexts.glyph";
const port = 8876;
const url = `http://127.0.0.1:${port}`;
const logs = [];
const child = spawn("python3", ["glyph.py", source], {
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

async function stopProcess() {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    new Promise(resolve => setTimeout(resolve, 1500)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

async function waitForServer() {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`);
      if (response.ok) {
        const state = await response.json();
        if (state.status === "ready") return state;
      }
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Glyph server did not become ready\n${logs.join("")}`);
}

function actionDisplay(value) {
  if (typeof value === "string") return value.trim();
  return String(value?.display || value?.expression || "").trim();
}

async function waitForProjection(page, expectedById) {
  await page.waitForFunction(expected => {
    const clusters = [...document.querySelectorAll(".transition-io-cluster")];
    if (clusters.length !== Object.keys(expected).length) return false;
    return clusters.every(cluster => (
      (cluster.dataset.actionValue || "") === expected[cluster.dataset.transitionId]
    ));
  }, expectedById, { timeout: 60_000 });
}

async function compileSource(page, sourceText) {
  await page.locator("#editor").fill(sourceText);
  const outcome = await page.evaluate(async expected => {
    clearTimeout(previewTimer);
    previewTimer = null;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60_000);
    try {
      const response = await fetch("/api/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: expected }),
        signal: controller.signal,
      });
      const next = await response.json();
      if (!response.ok) {
        return { status: "error", source: null, diagnostics: JSON.stringify(next) };
      }
      snapshot = next;
      render();
      window.GlyphExecutionContext?.refresh?.();
      return {
        status: next.status || "",
        source: next.source ?? null,
        diagnostics: (next.diagnostics || []).map(item => item.message || String(item)).join("\n"),
      };
    } catch (error) {
      return {
        status: "error",
        source: null,
        diagnostics: error?.name === "AbortError" ? "Preview request timed out" : String(error),
      };
    } finally {
      clearTimeout(timeout);
    }
  }, sourceText);
  assert.notEqual(
    outcome.status,
    "error",
    `Glyph compilation failed instead of updating the execution context:\n${outcome.diagnostics}`,
  );
  assert.equal(outcome.status, "ready", `unexpected preview status: ${outcome.status}`);
  assert.equal(outcome.source, sourceText, "compiled snapshot did not accept the requested source");
}

function expectedActions(machine, system) {
  return Object.fromEntries(machine.transitions.map(transition => {
    const binding = (transition.execution_action_bindings || []).find(item => item.system === system);
    assert(binding, `${transition.id}: missing ${system} binding`);
    return [transition.id, actionDisplay(binding.action)];
  }));
}

const apiState = await waitForServer();
const machine = apiState.views.state.machines.find(item => item.name === "Door");
assert(machine, "Door machine is missing");
assert(machine.transitions.length > 0);
for (const transition of machine.transitions) {
  assert.equal(transition.machine_action, null);
  assert.equal(transition.display_action, null);
  assert.equal(transition.action, null);
  assert.deepEqual(
    new Set((transition.execution_action_bindings || []).map(item => item.system)),
    new Set(["DoorControl", "DoorAudit"]),
  );
  assert.deepEqual(
    new Set((transition.execution_contexts || []).map(item => item.system)),
    new Set(["DoorControl", "DoorAudit"]),
  );
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  const pageErrors = [];
  const consoleErrors = [];
  page.on("pageerror", error => pageErrors.push(String(error)));
  page.on("console", message => { if (message.type() === "error") consoleErrors.push(message.text()); });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(count => (
    document.querySelectorAll(".transition-io-cluster").length === count
  ), machine.transitions.length, { timeout: 60_000 });
  await page.waitForSelector("#execution-context-select", { state: "attached", timeout: 60_000 });

  const optionLabels = await page.locator("#execution-context-select option").allTextContents();
  assert.deepEqual(optionLabels, [
    "自動（一致する場合のみ）",
    "Machineのみ",
    "DoorAudit / audit_control",
    "DoorControl / control",
  ]);

  const noActions = Object.fromEntries(machine.transitions.map(item => [item.id, ""]));
  await waitForProjection(page, noActions);

  await page.selectOption("#execution-context-select", { label: "Machineのみ" });
  await waitForProjection(page, noActions);

  const controlActions = expectedActions(machine, "DoorControl");
  await page.selectOption("#execution-context-select", { label: "DoorControl / control" });
  await waitForProjection(page, controlActions);
  assert(Object.values(controlActions).every(value => value.startsWith("actuator(DoorState(")));

  const svg = await page.evaluate(() => window.svg());
  for (const action of Object.values(controlActions)) {
    assert(svg.includes(action), `selected execution Action missing from SVG: ${action}`);
  }

  const auditActions = expectedActions(machine, "DoorAudit");
  await page.selectOption("#execution-context-select", { label: "DoorAudit / audit_control" });
  await waitForProjection(page, auditActions);
  assert(Object.values(auditActions).every(value => value.startsWith("audit(DoorState(")));

  const browserState = await page.evaluate(async () => (await fetch("/api/state")).json());
  const browserMachine = browserState.views.state.machines.find(item => item.name === "Door");
  assert(browserMachine.transitions.every(item => item.action === null));
  assert(browserMachine.transitions.every(item => item.execution_action_bindings.length === 2));

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(() => (
    document.querySelector("#execution-context-select")?.selectedOptions?.[0]?.textContent
      === "DoorAudit / audit_control"
  ), null, { timeout: 60_000 });
  await waitForProjection(page, auditActions);

  await page.click("#glyph-settings");
  await page.waitForFunction(() => document.querySelector("#glyph-settings-dialog")?.open === true);
  await page.selectOption("#glyph-language", "en");
  await page.waitForFunction(() => (
    document.querySelector("#execution-context-control label")?.textContent === "Execution context"
    && [...document.querySelectorAll("#execution-context-select option")]
      .some(option => option.textContent === "Machine only")
  ), null, { timeout: 60_000 });
  await page.click("#glyph-settings-close");
  await page.waitForFunction(() => document.querySelector("#glyph-settings-dialog")?.open === false);

  const blocked = await page.evaluate(() => {
    const unsafe = {
      machine_action: null,
      machine_action_invocations: [],
      machine_effect_invocations: [],
      execution_contexts: [{
        scope: "system",
        system: "UnsafeSystem",
        entry: "run",
        status: "unresolved",
        action: { display: "unsafe_action()" },
        action_invocations: [{ expression: "unsafe_action()" }],
        effect_invocations: [{ expression: "unsafe_action()" }],
      }],
    };
    return window.GlyphExecutionContext.projectionFor(
      unsafe,
      "context:system:UnsafeSystem:run",
    );
  });
  assert.equal(blocked.blocked, true);
  assert.equal(blocked.action, null);
  assert.deepEqual(blocked.invocations, []);
  assert.deepEqual(blocked.effects, []);

  const missing = await page.evaluate(() => window.GlyphExecutionContext.projectionFor({
    machine_action: { display: "machine_action()" },
    machine_action_invocations: [{ expression: "machine_action()" }],
    machine_effect_invocations: [{ expression: "machine_action()" }],
    execution_contexts: [],
  }, "context:system:MissingSystem:run"));
  assert.equal(missing.status, "missing");
  assert.equal(missing.blocked, true);
  assert.equal(missing.action, null);
  assert.deepEqual(missing.invocations, []);
  assert.deepEqual(missing.effects, []);

  const originalSource = await page.locator("#editor").inputValue();
  const actionlessSource = originalSource
    .replace("  audit_control -> audit\n", "")
    .replace("  audit(next)\n", "  Receipt(next)\n");
  assert.notEqual(actionlessSource, originalSource, "actionless route replacement did not match source");
  await compileSource(page, actionlessSource);
  await page.waitForFunction(() => (
    [...document.querySelectorAll("#execution-context-select option")]
      .some(option => option.textContent === "DoorAudit / audit_control (no System Action)")
  ), null, { timeout: 60_000 });
  await page.selectOption("#execution-context-select", {
    label: "DoorAudit / audit_control (no System Action)",
  });
  await waitForProjection(page, noActions);

  const renamedSource = actionlessSource.replace("system DoorAudit\n", "system DoorObserve\n");
  assert.notEqual(renamedSource, actionlessSource, "system rename did not match source");
  await compileSource(page, renamedSource);
  await page.waitForFunction(() => {
    const labels = [...document.querySelectorAll("#execution-context-select option")]
      .map(option => option.textContent);
    return labels.includes("DoorObserve / audit_control (no System Action)")
      && !labels.some(label => label.startsWith("DoorAudit /"));
  }, null, { timeout: 60_000 });
  await waitForProjection(page, noActions);

  let delayedSaveSeen = false;
  await page.route("**/api/save", async route => {
    delayedSaveSeen = true;
    await new Promise(resolve => setTimeout(resolve, 500));
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: "stale save failure" }),
    });
  });
  const raceSource = `${renamedSource}\n# stale-save-race\n`;
  await page.locator("#editor").fill(raceSource);
  await page.click("#save");
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "busy");
  await page.click("#compile");
  await page.waitForFunction(expected => (
    snapshot?.source === expected
    && document.querySelector("#status")?.textContent === "ready"
  ), raceSource, { timeout: 60_000 });
  await new Promise(resolve => setTimeout(resolve, 700));
  assert.equal(delayedSaveSeen, true);
  assert.equal(await page.locator("#status").textContent(), "ready");
  await page.unroute("**/api/save");

  const expectedConsoleError = message => (
    message.startsWith("StateTransitionIR rendering failed TypeError: Failed to fetch")
    || message.startsWith("transition label layout failed TypeError: Failed to fetch")
    || message.startsWith("initial transition routing failed TypeError: Failed to fetch")
    || message.startsWith("transition label layout failed NoModificationAllowedError:")
    || message.startsWith("transition layout transaction failed TypeError: Failed to fetch")
    || message.startsWith("transition layout transaction failed Error: no valid position exists inside the transition tether")
    || message.startsWith("enabling-case rendering failed TypeError: Failed to fetch")
    || message.startsWith("Failed to load resource: the server responded with a status of 500")
  );
  const unexpectedConsoleErrors = consoleErrors.filter(message => !expectedConsoleError(message));
  assert.deepEqual(pageErrors, [], `browser page errors:\n${pageErrors.join("\n")}`);
  assert.deepEqual(
    unexpectedConsoleErrors,
    [],
    `unexpected browser console errors:\n${unexpectedConsoleErrors.join("\n")}`,
  );
  await page.close();
} finally {
  await browser.close();
  await stopProcess();
}

console.log("verified complete, safe, live, localized execution-context selection and SVG projection");
