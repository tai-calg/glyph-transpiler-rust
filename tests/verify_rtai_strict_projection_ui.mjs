import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/rtai-strict-projection");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 180; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`strict app exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`);
      if (response.ok) {
        const state = await response.json();
        if (state.status === "ready") return state;
        if (state.status === "error") throw new Error(JSON.stringify(state.diagnostics));
      }
    } catch (error) {
      if (attempt > 170) throw error;
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`strict app did not become ready\n${logs.join("")}`);
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

const port = 8896;
const logs = [];
const child = spawn(
  "python3",
  ["tests/run_rtai_strict_diagram_app.py", "examples/acceptance/rtai_strict_projection.glyph"],
  {
    env: {
      ...process.env,
      GLYPH_DIAGRAM_PORT: String(port),
      GLYPH_DIAGRAM_NO_BROWSER: "1",
      PYTHONUNBUFFERED: "1",
    },
    stdio: ["ignore", "pipe", "pipe"],
  },
);
child.stdout.on("data", chunk => logs.push(chunk.toString()));
child.stderr.on("data", chunk => logs.push(chunk.toString()));

const url = `http://127.0.0.1:${port}`;
const browser = await chromium.launch({ headless: true });
try {
  const state = await waitForServer(url, child, logs);
  const views = state.views;
  assert.equal(views.rtai_projection_mode, "strict-exact");
  assert.equal(views.rtai_legacy_system_action_analyzer_enabled, false);
  assert.equal(views.strict_projection_campaign?.ready, true, JSON.stringify(views.strict_projection_campaign));
  assert.equal(views.strict_projection_campaign?.legacy_fallback_allowed, false);

  const machine = views.state.machines[0];
  assert(machine, "strict UI campaign has no machine");
  assert(machine.transitions.length > 0, "strict UI campaign has no transitions");
  for (const transition of machine.transitions) {
    assert.equal(transition.rtai_semantic_status?.status, "exact");
    assert.equal(transition.legacy_system_action_fallback_allowed, false);
    assert.equal(transition.system_action_projection_source, "rtai-execution-evidence-v2");
    assert(transition.system_action, `${transition.id}: native System Action missing`);
    assert.equal(transition.execution_evidence_v2, undefined);
    assert.deepEqual(transition.execution_action_bindings, []);
    assert.deepEqual(transition.execution_contexts, []);
  }

  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(expected => {
    const stage = document.querySelector(".graph-stage");
    return stage?.dataset.stateTransitionIRV4LabelsReady === "true"
      && stage?.dataset.transitionIoClustersReady === "true"
      && stage?.dataset.rtaiSemanticStatusReady === "true"
      && stage?.dataset.rtaiProjectionMode === "strict-exact"
      && document.querySelectorAll(".transition-io-cluster > .rtai-semantic-badge.exact").length === expected;
  }, machine.transitions.length, { timeout: 60_000 });

  const badges = await page.locator(".transition-io-cluster > .rtai-semantic-badge.exact").evaluateAll(elements => (
    elements.map(element => {
      const style = getComputedStyle(element);
      return {
        status: element.dataset.rtaiSemanticStatus,
        label: element.textContent,
        reason: element.dataset.rtaiSemanticReason,
        title: element.title,
        visible: style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) > 0,
      };
    })
  ));
  assert.equal(badges.length, machine.transitions.length);
  assert(badges.every(item => item.status === "exact"));
  assert(badges.every(item => item.label === "Exact"));
  assert(badges.every(item => item.reason.length > 0));
  assert(badges.every(item => item.title.includes("Exact")));
  assert(badges.every(item => item.visible), JSON.stringify(badges));

  const renderedActions = await page.locator('.transition-io-node[data-io-kind="io"]').evaluateAll(elements => (
    elements.map(element => element.closest(".transition-io-cluster")?.dataset.actionValue || "")
  ));
  assert.equal(renderedActions.length, machine.transitions.length);
  assert(renderedActions.every(value => value.includes("actuator")), renderedActions.join("\n"));

  await page.screenshot({
    path: path.join(outputDirectory, "strict-ui.png"),
    fullPage: true,
  });
  await fs.writeFile(
    path.join(outputDirectory, "strict-ui-report.json"),
    `${JSON.stringify({
      ready: true,
      machine: machine.name,
      transition_count: machine.transitions.length,
      badges,
      rendered_actions: renderedActions,
    }, null, 2)}\n`,
  );
  console.log(JSON.stringify({ ready: true, transitionCount: machine.transitions.length }));
} finally {
  await browser.close();
  await stopProcess(child);
}
