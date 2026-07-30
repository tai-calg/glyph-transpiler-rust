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
  await page.click("#compile");
  await page.waitForFunction(expected => {
    const status = document.querySelector("#status")?.textContent;
    if (status === "error") return true;
    return status === "ready"
      && typeof snapshot === "object"
      && snapshot?.source === expected;
  }, sourceText, { timeout: 60_000 });
  const outcome = await page.evaluate(() => ({
    status: document.querySelector("#status")?.textContent || "",
    source: typeof snapshot === "object" ? snapshot?.source : null,
    diagnostics: document.querySelector("#diagnostics")?.textContent || "",
  }));
  assert.notEqual(
    outcome.status,
    "error",
    `Glyph compilation failed instead of updating the execution context:\n${outcome.diagnostics}`,
  );
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
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(count => (
    document.querySelectorAll(".transition-io-cluster").length === count
    && document.querySelector("#execution-context-select")
  ), machine.transitions.length, { timeout: 60_000 });

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

  const originalSource = await page.locator("#editor").inputValue();
  const actionlessSource = originalSource.replace("  audit(next)\n", "  Receipt(next)\n");
  assert.notEqual(actionlessSource, originalSource, "audit action replacement did not match source");
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

  await page.close();
} finally {
  await browser.close();
  await stopProcess();
}

console.log("verified complete, safe, live, localized execution-context selection and SVG projection");
