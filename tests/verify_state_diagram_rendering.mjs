import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const cases = [
  {
    slug: "motor-safety",
    file: "examples/acceptance/motor_safety.glyph",
    machines: [{
      name: "Motor",
      states: ["Stopped", "Running", "Faulted"],
      warnings: ["state-independent-transition", "unreachable-branch"],
      requireInputAction: true,
      requireActionTargetIndependence: true,
      requireOperationAction: true,
    }],
  },
  {
    slug: "traffic-light",
    file: "examples/state_diagrams/traffic_light.glyph",
    machines: [{
      name: "Traffic",
      states: ["Red", "Green", "Yellow", "TrafficFault"],
      warnings: [
        "STIR_TRIGGER_AMBIGUOUS_FALLBACK",
        "STIR_TRIGGER_AMBIGUOUS_FALLBACK",
        "STIR_TRIGGER_AMBIGUOUS_FALLBACK",
        "STIR_TRIGGER_AMBIGUOUS_FALLBACK",
      ],
      provisionalTriggers: 7,
    }],
  },
  {
    slug: "session-protocol",
    file: "examples/state_diagrams/session_protocol.glyph",
    machines: [{
      name: "Session",
      states: ["SessionIdle", "SessionConnecting", "SessionReady", "SessionFailed"],
      warnings: [],
      provisionalTriggers: 0,
    }],
  },
  {
    slug: "dual-machines",
    file: "examples/state_diagrams/dual_machines.glyph",
    machines: [
      {
        name: "Door",
        states: ["DoorClosed", "DoorOpen", "DoorJammed"],
        warnings: ["unreachable-state"],
        provisionalTriggers: 0,
      },
      {
        name: "Power",
        states: ["PowerOff", "PowerOn", "PowerFault"],
        warnings: [],
        provisionalTriggers: 0,
      },
    ],
  },
];

const outputDirectory = path.resolve("build/state-diagram-regression");
await fs.mkdir(outputDirectory, { recursive: true });
const sorted = values => [...values].sort((left, right) => left.localeCompare(right));

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph process exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`, { cache: "no-store" });
      if (response.ok && (await response.json()).status === "ready") return await (await fetch(`${url}/api/state`, { cache: "no-store" })).json();
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Glyph diagram server did not become ready\n${logs.join("")}`);
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

async function waitForOrdinaryLayout(page, machineName, transitionCount) {
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
    positions: [...document.querySelectorAll(".transition-io-cluster")].map(cluster => [
      cluster.dataset.transitionId,
      cluster.style.left,
      cluster.style.top,
      cluster.dataset.ioValue,
    ]),
    paths: [...document.querySelectorAll(".state-transition-path")].map(item => item.getAttribute("d") || ""),
  }));
  const before = await snapshot();
  await page.waitForTimeout(100);
  const after = await snapshot();
  assert.deepEqual(after, before, `${machineName}: ordinary layout kept moving after readiness`);
}

async function assertOrdinaryGeometry(page, machineName) {
  const audit = await page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    if (!stage) return { error: "graph stage is missing" };
    const clusters = [...stage.querySelectorAll(".transition-io-cluster")];
    return {
      profile: stage.dataset.transitionLayoutProfile || "",
      mode: stage.dataset.transitionLayoutMode || "",
      denseCanvas: stage.dataset.transitionDenseCanvas || "",
      layoutBudgetMs: Number(stage.dataset.transitionLayoutBudgetMs || 0),
      renderBudgetMs: Number(stage.dataset.transitionIoRenderBudgetMs || 0),
      renderDurationMs: Number(stage.dataset.transitionIoRenderDurationMs || 0),
      renderBudgetExceeded: stage.dataset.transitionIoRenderBudgetExceeded || "",
      error: stage.dataset.transitionLayoutError || "",
      maximumDistance: Math.max(0, ...clusters.map(cluster => Number(cluster.dataset.ioDistance || 0))),
      distanceLimit: Number(stage.dataset.transitionIoMaxDistance || 0),
      fatalText: document.body.textContent?.includes("State diagram certification failed") || false,
      certificatePresent: Boolean(window.glyphLayoutPublicationCertificate),
      initialRouterPresent: Boolean(window.glyphInitialTransitionRouter),
    };
  });
  assert.equal(audit.error, undefined, `${machineName}: ${audit.error}`);
  assert.equal(audit.profile, "ordinary", JSON.stringify(audit));
  assert.equal(audit.mode, "base", JSON.stringify(audit));
  assert.equal(audit.denseCanvas, "disabled", JSON.stringify(audit));
  assert.equal(audit.layoutBudgetMs, 48, JSON.stringify(audit));
  assert.equal(audit.renderBudgetMs, 16, JSON.stringify(audit));
  assert.equal(audit.error, "", JSON.stringify(audit));
  assert.equal(audit.fatalText, false, JSON.stringify(audit));
  assert.equal(audit.certificatePresent, false, JSON.stringify(audit));
  assert.equal(audit.initialRouterPresent, false, JSON.stringify(audit));
  assert(audit.maximumDistance <= audit.distanceLimit + 0.5, `${machineName}: label escaped its arrow bound: ${JSON.stringify(audit)}`);
}

function actionDisplay(transition) {
  const raw = transition?.action;
  if (typeof raw === "string") return raw.trim();
  return String(raw?.display || raw?.expression || "").trim();
}

function emittedOutputDisplay(transition) {
  const raw = transition?.emitted_output;
  return String(raw?.display || raw?.expression || "").trim();
}

const browser = await chromium.launch({ headless: true });
try {
  let port = 8765;
  for (const testCase of cases) {
    const logs = [];
    const child = spawn("python3", ["glyph.py", testCase.file], {
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

    const url = `http://127.0.0.1:${port}`;
    try {
      const apiState = await waitForServer(url, child, logs);
      assert.equal(apiState.views.schema, "glyph.io-state-views");
      assert.equal(apiState.views.state_transition_ir.version, 4);
      assert.equal(apiState.views.state.machines.length, testCase.machines.length);

      const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
      const browserErrors = [];
      page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
      page.on("console", message => {
        if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
      });
      await page.goto(url, { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
      await page.click('button[data-tab="state"]');

      const options = await page.locator("#machine-select option").allTextContents();
      assert.deepEqual(sorted(options), sorted(testCase.machines.map(machine => machine.name)));

      for (const expected of testCase.machines) {
        const machine = apiState.views.state.machines.find(item => item.name === expected.name);
        assert(machine, `${testCase.slug}/${expected.name}: API machine missing`);
        if (testCase.machines.length > 1) await page.selectOption("#machine-select", { label: expected.name });
        await waitForOrdinaryLayout(page, expected.name, machine.transitions.length);

        assert.deepEqual(sorted(await page.locator(".state-name").allTextContents()), sorted(expected.states));
        assert.deepEqual(sorted(await page.locator(".analysis-code").allTextContents()), sorted(expected.warnings));
        assert.equal(await page.locator(".transition-io-cluster").count(), machine.transitions.length);
        assert.equal(await page.locator('.transition-io-node[data-io-kind="io"]').count(), machine.transitions.length);
        assert.equal(await page.locator(".state-transition-path").count(), machine.transitions.length);

        if (expected.requireActionTargetIndependence) {
          const independence = machine.analysis?.action_target_independence;
          assert(independence, `${testCase.slug}/${expected.name}: independence analysis missing`);
          assert.equal(independence.version, 1);
          assert.equal(independence.typed_independent, true);
          assert.equal(independence.behaviorally_independent, true);
          assert.notEqual(independence.mapping_shape, "one-to-one");
          assert.equal(independence.near_alias_count, 0);
          assert(independence.behavioral_witness_count > 0);
        }

        const combinedValues = await page.locator('.transition-io-node[data-io-kind="io"]').evaluateAll(elements => elements.map(element => {
          const cluster = element.closest(".transition-io-cluster");
          return {
            id: cluster?.dataset.transitionId || "",
            value: element.querySelector(".transition-io-value")?.textContent || "",
            input: cluster?.dataset.inputValue || "",
            action: cluster?.dataset.actionValue || "",
          };
        }));
        assert(combinedValues.every(({ value }) => value.trim().length > 0));
        for (const rendered of combinedValues) {
          const transition = machine.transitions.find(item => item.id === rendered.id);
          assert(transition, `${testCase.slug}/${expected.name}: missing transition ${rendered.id}`);
          const expectedAction = actionDisplay(transition);
          assert.equal(rendered.action, expectedAction, `${testCase.slug}/${expected.name}/${rendered.id}: DOM Action differs from StateTransitionIR`);
          assert.notEqual(rendered.action, String(transition.target_state || ""), `${testCase.slug}/${expected.name}/${rendered.id}: Target State leaked into Action`);
          const emittedOutput = emittedOutputDisplay(transition);
          if (rendered.action && emittedOutput) assert.notEqual(rendered.action, emittedOutput, `${testCase.slug}/${expected.name}/${rendered.id}: Emitted Output leaked into Action`);
          if (expectedAction) {
            assert.equal(transition.action?.provenance, "transition-operation-invocation");
            assert(Array.isArray(transition.action_invocations) && transition.action_invocations.length > 0);
            assert(rendered.value.includes(`➞ ${expectedAction}`));
          } else {
            assert(!rendered.value.includes("➞"));
          }
        }

        if (expected.requireOperationAction) {
          assert.equal(apiState.views.transition_operation_action_version, 2);
          assert.equal(machine.analysis.state_field_action_count, 0);
        }

        if (expected.requireInputAction) {
          const semanticPairs = combinedValues.filter(({ input, action, value }) => input.trim() && action.trim() && value.includes("➞"));
          assert(semanticPairs.length > 0, `${testCase.slug}/${expected.name}: no Input ➞ Action transition`);
          for (const rendered of semanticPairs) assert.notEqual(rendered.input, rendered.action);
        }

        if (expected.provisionalTriggers !== undefined) {
          assert.equal(await page.locator(".transition-io-cluster.provisional-trigger").count(), expected.provisionalTriggers);
        }

        const visibleLegacyLabels = await page.locator(".transition-label").evaluateAll(elements => elements.filter(element => {
          const style = getComputedStyle(element);
          return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0;
        }).length);
        assert.equal(visibleLegacyLabels, 0);
        await assertOrdinaryGeometry(page, expected.name);

        await page.screenshot({
          path: path.join(outputDirectory, `${testCase.slug}-${expected.name.toLowerCase()}.png`),
          fullPage: true,
        });
      }
      assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
      await page.close();
    } finally {
      await stopProcess(child);
      port += 1;
    }
  }
} finally {
  await browser.close();
}

console.log("verified compiler-derived state diagrams with bounded ordinary layout and operation-derived Actions");
