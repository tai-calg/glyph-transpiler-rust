import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const cases = [
  ["motor-safety", "examples/acceptance/motor_safety.glyph", [{ name: "Motor", states: ["Stopped", "Running", "Faulted"], warnings: ["state-independent-transition", "unreachable-branch"], requireOperationAction: true }]],
  ["traffic-light", "examples/state_diagrams/traffic_light.glyph", [{ name: "Traffic", states: ["Red", "Green", "Yellow", "TrafficFault"], warnings: ["STIR_TRIGGER_AMBIGUOUS_FALLBACK", "STIR_TRIGGER_AMBIGUOUS_FALLBACK", "STIR_TRIGGER_AMBIGUOUS_FALLBACK", "STIR_TRIGGER_AMBIGUOUS_FALLBACK"], provisional: 7 }]],
  ["session-protocol", "examples/state_diagrams/session_protocol.glyph", [{ name: "Session", states: ["SessionIdle", "SessionConnecting", "SessionReady", "SessionFailed"], warnings: [], provisional: 0 }]],
  ["dual-machines", "examples/state_diagrams/dual_machines.glyph", [
    { name: "Door", states: ["DoorClosed", "DoorOpen", "DoorJammed"], warnings: ["unreachable-state"], provisional: 0 },
    { name: "Power", states: ["PowerOff", "PowerOn", "PowerFault"], warnings: [], provisional: 0 },
  ]],
];

const outputDirectory = path.resolve("build/state-diagram-regression");
await fs.mkdir(outputDirectory, { recursive: true });
const sorted = values => [...values].sort((a, b) => a.localeCompare(b));
const actionDisplay = transition => typeof transition?.action === "string"
  ? transition.action.trim()
  : String(transition?.action?.display || transition?.action?.expression || "").trim();
const emittedOutput = transition => String(transition?.emitted_output?.display || transition?.emitted_output?.expression || "").trim();

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
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
  await Promise.race([new Promise(resolve => child.once("exit", resolve)), new Promise(resolve => setTimeout(resolve, 1500))]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

async function waitForOrdinary(page, machineName, transitionCount) {
  await page.waitForFunction(({ name, count }) => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return document.querySelector("#machine-select")?.selectedOptions?.[0]?.textContent === name
      && stage?.dataset.transitionIoClustersReady === "true"
      && stage?.dataset.transitionEnablingCasesReady === "true"
      && stage?.dataset.transitionLayoutState === "ready"
      && stage?.dataset.transitionPublicationReady === "true"
      && stage?.dataset.transitionLayoutProfile === "ordinary"
      && stage?.dataset.transitionLayoutMode === "base"
      && stage?.dataset.transitionDenseCanvas === "disabled"
      && !stage?.dataset.transitionLayoutError
      && stage.querySelectorAll(".transition-io-cluster").length === count;
  }, { name: machineName, count: transitionCount }, { timeout: 5000 });

  const snapshot = async () => page.evaluate(() => ({
    clusters: [...document.querySelectorAll(".transition-io-cluster")].map(item => [item.dataset.transitionId, item.style.left, item.style.top, item.dataset.ioValue]),
    paths: [...document.querySelectorAll(".state-transition-path")].map(item => item.getAttribute("d") || ""),
  }));
  const before = await snapshot();
  await page.waitForTimeout(100);
  assert.deepEqual(await snapshot(), before, `${machineName}: layout kept moving after ready`);
}

async function ordinaryAudit(page) {
  return page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const clusters = [...(stage?.querySelectorAll(".transition-io-cluster") || [])];
    return {
      stagePresent: Boolean(stage),
      profile: stage?.dataset.transitionLayoutProfile || "",
      mode: stage?.dataset.transitionLayoutMode || "",
      dense: stage?.dataset.transitionDenseCanvas || "",
      layoutBudgetMs: Number(stage?.dataset.transitionLayoutBudgetMs || 0),
      renderBudgetMs: Number(stage?.dataset.transitionIoRenderBudgetMs || 0),
      renderDurationMs: Number(stage?.dataset.transitionIoRenderDurationMs || 0),
      error: stage?.dataset.transitionLayoutError || "",
      maximumDistance: Math.max(0, ...clusters.map(item => Number(item.dataset.ioDistance || 0))),
      distanceLimit: Number(stage?.dataset.transitionIoMaxDistance || 0),
      fatalText: document.body.textContent?.includes("State diagram certification failed") || false,
      certificate: Boolean(window.glyphLayoutPublicationCertificate),
      router: Boolean(window.glyphInitialTransitionRouter),
    };
  });
}

const browser = await chromium.launch({ headless: true });
try {
  let port = 8765;
  for (const [slug, file, expectedMachines] of cases) {
    const logs = [];
    const child = spawn("python3", ["glyph.py", file], {
      env: { ...process.env, GLYPH_DIAGRAM_PORT: String(port), GLYPH_DIAGRAM_NO_BROWSER: "1", PYTHONUNBUFFERED: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    child.stdout.on("data", chunk => logs.push(chunk.toString()));
    child.stderr.on("data", chunk => logs.push(chunk.toString()));
    const url = `http://127.0.0.1:${port}`;
    try {
      const apiState = await waitForServer(url, child, logs);
      assert.equal(apiState.views.schema, "glyph.io-state-views");
      assert.equal(apiState.views.state_transition_ir.version, 4);
      assert.equal(apiState.views.state.machines.length, expectedMachines.length);

      const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
      const errors = [];
      page.on("pageerror", error => errors.push(`pageerror: ${error.message}`));
      page.on("console", message => { if (message.type() === "error") errors.push(`console: ${message.text()}`); });
      await page.goto(url, { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
      await page.click('button[data-tab="state"]');
      assert.deepEqual(sorted(await page.locator("#machine-select option").allTextContents()), sorted(expectedMachines.map(item => item.name)));

      for (const expected of expectedMachines) {
        const machine = apiState.views.state.machines.find(item => item.name === expected.name);
        assert(machine, `${slug}/${expected.name}: machine missing`);
        if (expectedMachines.length > 1) await page.selectOption("#machine-select", { label: expected.name });
        await waitForOrdinary(page, expected.name, machine.transitions.length);
        assert.deepEqual(sorted(await page.locator(".state-name").allTextContents()), sorted(expected.states));
        assert.deepEqual(sorted(await page.locator(".analysis-code").allTextContents()), sorted(expected.warnings));
        assert.equal(await page.locator(".transition-io-cluster").count(), machine.transitions.length);
        assert.equal(await page.locator(".state-transition-path").count(), machine.transitions.length);
        if (expected.provisional !== undefined) assert.equal(await page.locator(".transition-io-cluster.provisional-trigger").count(), expected.provisional);

        const rendered = await page.locator(".transition-io-cluster").evaluateAll(elements => elements.map(cluster => ({
          id: cluster.dataset.transitionId || "",
          value: cluster.dataset.ioValue || "",
          input: cluster.dataset.inputValue || "",
          action: cluster.dataset.actionValue || "",
        })));
        assert(rendered.every(item => item.value.trim()));
        for (const item of rendered) {
          const transition = machine.transitions.find(candidate => candidate.id === item.id);
          assert(transition, `${slug}/${expected.name}: transition ${item.id} missing`);
          const action = actionDisplay(transition);
          assert.equal(item.action, action, `${slug}/${expected.name}/${item.id}: Action mismatch`);
          assert.notEqual(item.action, String(transition.target_state || ""), `${slug}/${expected.name}/${item.id}: Target State leaked into Action`);
          if (item.action && emittedOutput(transition)) assert.notEqual(item.action, emittedOutput(transition), `${slug}/${expected.name}/${item.id}: Emitted Output leaked into Action`);
          if (action) assert(item.value.includes(`➞ ${action}`));
          else assert(!item.value.includes("➞"));
        }
        if (expected.requireOperationAction) {
          assert.equal(apiState.views.transition_operation_action_version, 2);
          assert.equal(machine.analysis.state_field_action_count, 0);
          assert(rendered.some(item => item.input && item.action && item.value.includes("➞")));
        }

        const audit = await ordinaryAudit(page);
        assert.equal(audit.stagePresent, true, JSON.stringify(audit));
        assert.equal(audit.profile, "ordinary", JSON.stringify(audit));
        assert.equal(audit.mode, "base", JSON.stringify(audit));
        assert.equal(audit.dense, "disabled", JSON.stringify(audit));
        assert.equal(audit.layoutBudgetMs, 48, JSON.stringify(audit));
        assert.equal(audit.renderBudgetMs, 16, JSON.stringify(audit));
        assert.equal(audit.error, "", JSON.stringify(audit));
        assert.equal(audit.fatalText, false, JSON.stringify(audit));
        assert.equal(audit.certificate, false, JSON.stringify(audit));
        assert.equal(audit.router, false, JSON.stringify(audit));
        assert(audit.maximumDistance <= audit.distanceLimit + 0.5, JSON.stringify(audit));
        await page.screenshot({ path: path.join(outputDirectory, `${slug}-${expected.name.toLowerCase()}.png`), fullPage: true });
      }
      assert.deepEqual(errors, [], errors.join("\n"));
      await page.close();
    } finally {
      await stop(child);
      port += 1;
    }
  }
} finally {
  await browser.close();
}

console.log("verified compiler-derived state diagrams with bounded ordinary layout and operation-derived Actions");
