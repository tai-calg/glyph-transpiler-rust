import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const port = 8891;
const url = `http://127.0.0.1:${port}`;
const logs = [];
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

async function stopProcess() {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    new Promise(resolve => setTimeout(resolve, 1500)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

async function waitForState() {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`, { cache: "no-store" });
      if (response.ok) {
        const value = await response.json();
        if (value.status === "ready") return value;
      }
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Glyph server did not become ready\n${logs.join("")}`);
}

function actionDisplay(transition) {
  const action = transition?.action;
  if (typeof action === "string") return action.trim();
  return String(action?.display || action?.expression || "").trim();
}

const browser = await chromium.launch({ headless: true });
try {
  const apiState = await waitForState();
  assert.equal(apiState.views.transition_enabling_case_version, 1);
  const machine = apiState.views.state.machines.find(item => item.name === "Motor");
  assert(machine);

  const transitionByAction = action => machine.transitions.find(
    transition => actionDisplay(transition) === action,
  );

  const emergency = transitionByAction("EmergencyBrake");
  assert(emergency);
  assert.equal(emergency.enabling_cases.length, 1);
  assert.equal(emergency.enabling_cases[0].input_pattern.expression, "input.emergency");
  assert.equal(emergency.enabling_cases[0].guard.display, "!input.fault");
  assert.equal(
    emergency.enabling_cases[0].exact_enabling_condition.expression,
    "input.emergency&!input.fault",
  );

  const disabled = transitionByAction("DisableMotor");
  assert(disabled);
  assert.equal(disabled.enabling_cases[0].input_pattern.expression, "!input.enabled");
  assert.equal(
    disabled.enabling_cases[0].guard.display,
    "!(input.fault|input.emergency)",
  );

  const running = transitionByAction("SetMotorPower(normalize(input.raw))");
  assert(running);
  assert.equal(running.enabling_cases[0].input_pattern, null);
  assert.equal(running.enabling_cases[0].guard.display, "otherwise");
  assert.equal(running.enabling_cases[0].fallback, true);

  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(() => {
    const stage = document.querySelector(".graph-stage");
    return stage?.dataset.transitionEnablingCasesReady === "true"
      && stage.querySelectorAll(".transition-enabling-case-line").length > 0;
  });

  const renderedCases = await page.locator(".transition-enabling-case-line").evaluateAll(elements => (
    elements.map(element => ({
      id: element.dataset.enablingCaseId || "",
      input: element.dataset.inputValue || "",
      guard: element.dataset.guardValue || "",
      action: element.dataset.actionValue || "",
      exact: element.dataset.exactEnablingCondition || "",
      value: element.textContent || "",
    }))
  ));

  const emergencyDom = renderedCases.find(item => item.action === "EmergencyBrake");
  assert(emergencyDom);
  assert.equal(emergencyDom.input, "input.emergency");
  assert.equal(emergencyDom.guard, "!input.fault");
  assert.equal(emergencyDom.exact, "input.emergency&!input.fault");
  assert.equal(emergencyDom.value, "input.emergency [!input.fault] ➞ EmergencyBrake");
  assert(!emergencyDom.input.includes("input.fault"));

  const disabledDom = renderedCases.find(item => item.action === "DisableMotor");
  assert(disabledDom);
  assert.equal(disabledDom.input, "!input.enabled");
  assert.equal(disabledDom.guard, "!(input.fault|input.emergency)");
  assert(!disabledDom.input.includes("input.fault"));
  assert(!disabledDom.input.includes("input.emergency"));

  const runningDom = renderedCases.find(
    item => item.action === "SetMotorPower(normalize(input.raw))",
  );
  assert(runningDom);
  assert.equal(runningDom.input, "");
  assert.equal(runningDom.guard, "otherwise");
  assert.equal(
    runningDom.value,
    "[otherwise] ➞ SetMotorPower(normalize(input.raw))",
  );
  assert(!runningDom.value.startsWith("otherwise ➞"));

  await page.close();
} finally {
  await browser.close();
  await stopProcess();
}

console.log("verified compiler-owned transition Enabling Cases and separated Input/Guard DOM roles");
