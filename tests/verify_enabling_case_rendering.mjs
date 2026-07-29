import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const file = "examples/acceptance/motor_safety.glyph";
const port = 8871;
const url = `http://127.0.0.1:${port}`;
const logs = [];

async function waitForServer(child) {
  for (let attempt = 0; attempt < 160; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`, { cache: "no-store" });
      if (response.ok) {
        const state = await response.json();
        if (state.status === "ready") return state;
      }
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Glyph server did not become ready\n${logs.join("")}`);
}

async function stop(child) {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    new Promise(resolve => setTimeout(resolve, 1500)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

function actionVariant(transition) {
  return String(transition?.action?.variant || "");
}

function onlyCase(machine, action) {
  const transition = machine.transitions.find(item => actionVariant(item) === action);
  assert(transition, `missing transition action ${action}`);
  assert.equal(transition.enabling_cases.length, 1, `${action} must have one enabling case`);
  return { transition, item: transition.enabling_cases[0] };
}

const child = spawn("python3", ["glyph.py", file], {
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
  const apiState = await waitForServer(child);
  assert.equal(apiState.views.state_transition_ir.version, 4);
  assert.equal(apiState.views.transition_enabling_cases_version, 1);
  const machine = apiState.views.state.machines.find(item => item.name === "Motor");
  assert(machine, "Motor machine missing");
  assert.equal(machine.analysis.all_transitions_have_enabling_cases, true);

  const fault = onlyCase(machine, "LatchFault");
  assert.equal(fault.item.input_pattern.expression, "input.fault");
  assert.equal(fault.item.guard, null);

  const emergency = onlyCase(machine, "EmergencyBrake");
  assert.equal(emergency.item.input_pattern.expression, "input.emergency");
  assert.equal(emergency.item.guard.expression, "!input.fault");
  assert.equal(emergency.item.guard.terms[0].origin, "priority-exclusion");
  assert.equal(emergency.item.enabling_condition.expression, "input.emergency&!input.fault");
  assert(!emergency.item.input_pattern.expression.includes("!input.fault"));

  const disabled = onlyCase(machine, "DisableMotor");
  assert.equal(disabled.item.input_pattern.expression, "!input.enabled");
  assert.equal(disabled.item.guard.expression, "!(input.fault|input.emergency)");

  const running = onlyCase(machine, "SetMotorPower");
  assert.equal(running.item.input_pattern, null);
  assert.equal(running.item.guard.display, "otherwise");
  assert.equal(running.item.guard.terms[0].origin, "fallback");

  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(() => (
    document.querySelector(".graph-stage")?.dataset.transitionEnablingCasesReady === "true"
  ));

  const rendered = await page.locator(".transition-io-cluster").evaluateAll(elements => (
    elements.map(element => ({
      id: element.dataset.transitionId || "",
      input: element.dataset.inputValue || "",
      guard: element.dataset.guardValue || "",
      action: element.dataset.actionValue || "",
      value: element.dataset.ioValue || "",
      count: element.dataset.enablingCaseCount || "",
    }))
  ));

  const byId = id => rendered.find(item => item.id === id);
  const emergencyDom = byId(emergency.transition.id);
  assert(emergencyDom, "EmergencyBrake DOM cluster missing");
  assert.deepEqual(
    {
      input: emergencyDom.input,
      guard: emergencyDom.guard,
      action: emergencyDom.action,
      count: emergencyDom.count,
    },
    {
      input: "input.emergency",
      guard: "!input.fault",
      action: "EmergencyBrake",
      count: "1",
    },
  );
  assert.equal(
    emergencyDom.value,
    "input.emergency [!input.fault] ➞ EmergencyBrake",
  );
  assert(!emergencyDom.input.includes("!input.fault"));

  const runningDom = byId(running.transition.id);
  assert(runningDom, "SetMotorPower DOM cluster missing");
  assert.equal(runningDom.input, "");
  assert.equal(runningDom.guard, "otherwise");
  assert.equal(runningDom.action, "SetMotorPower(normalize(input.raw))");
  assert.equal(
    runningDom.value,
    "[otherwise] ➞ SetMotorPower(normalize(input.raw))",
  );

  await page.close();
} finally {
  await browser.close();
  await stop(child);
}

console.log("verified enabling-case Input Pattern, Guard, Action, and fallback DOM roles");
