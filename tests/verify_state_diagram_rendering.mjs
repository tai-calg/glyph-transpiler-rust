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
      warnings: ["state-independent-transition", "unreachable-branch", "unreachable-state"],
      requireInputAction: true,
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
      const response = await fetch(`${url}/api/state`);
      if (response.ok) {
        const state = await response.json();
        if (state.status === "ready") return state;
      }
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

async function assertDiagramGeometry(page) {
  const geometry = await page.evaluate(() => {
    const stage = document.querySelector(".graph-stage");
    const stageRect = stage?.getBoundingClientRect();
    if (!stage || !stageRect) return { error: "graph stage is missing" };
    const nodes = [...stage.querySelectorAll(".state-node")].map(element => element.getBoundingClientRect());
    const clusters = [...stage.querySelectorAll(".transition-io-cluster")].map(element => ({
      id: element.dataset.transitionId,
      distance: Number(element.dataset.ioDistance || 0),
      rect: element.getBoundingClientRect(),
    }));
    const overlaps = (left, right, gap = 1) => !(
      left.right <= right.left + gap || right.right <= left.left + gap
      || left.bottom <= right.top + gap || right.bottom <= left.top + gap
    );
    const collisions = [];
    clusters.forEach((cluster, index) => {
      clusters.slice(index + 1).forEach(other => {
        if (overlaps(cluster.rect, other.rect)) collisions.push(`${cluster.id}/${other.id}`);
      });
      nodes.forEach((node, nodeIndex) => {
        if (overlaps(cluster.rect, node)) collisions.push(`${cluster.id}/node-${nodeIndex}`);
      });
    });
    const outside = clusters.filter(({rect}) => (
      rect.left < stageRect.left - 1 || rect.top < stageRect.top - 1
      || rect.right > stageRect.right + 1 || rect.bottom > stageRect.bottom + 1
    )).map(item => item.id);
    return { collisions, outside, distances: clusters.map(item => item.distance) };
  });
  assert.equal(geometry.error, undefined, geometry.error);
  assert.deepEqual(geometry.collisions, [], `I/O collisions: ${JSON.stringify(geometry.collisions)}`);
  assert.deepEqual(geometry.outside, [], `I/O outside stage: ${JSON.stringify(geometry.outside)}`);
  assert(geometry.distances.every(value => value <= 96.5), `I/O escaped tether: ${geometry.distances.join(", ")}`);
}

function actionDisplay(transition) {
  const raw = transition?.action;
  if (typeof raw === "string") return raw.trim();
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
      await page.goto(url, { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
      await page.click('button[data-tab="state"]');

      const options = await page.locator("#machine-select option").allTextContents();
      assert.deepEqual(sorted(options), sorted(testCase.machines.map(machine => machine.name)));

      for (const expected of testCase.machines) {
        const machine = apiState.views.state.machines.find(item => item.name === expected.name);
        assert(machine, `${testCase.slug}/${expected.name}: API machine missing`);
        if (testCase.machines.length > 1) await page.selectOption("#machine-select", { label: expected.name });
        await page.waitForFunction(({machineName, transitionCount}) => {
          const stage = document.querySelector(".graph-stage");
          return document.querySelector("#machine-select")?.selectedOptions?.[0]?.textContent === machineName
            && stage?.dataset.transitionIoClustersReady === "true"
            && stage?.dataset.transitionIoCollisionSolved === "true"
            && stage.querySelectorAll(".transition-io-cluster").length === transitionCount;
        }, { machineName: expected.name, transitionCount: machine.transitions.length });

        assert.deepEqual(sorted(await page.locator(".state-name").allTextContents()), sorted(expected.states));
        assert.deepEqual(sorted(await page.locator(".analysis-code").allTextContents()), sorted(expected.warnings));
        assert.equal(await page.locator(".transition-io-cluster").count(), machine.transitions.length);
        assert.equal(await page.locator('.transition-io-node[data-io-kind="io"]').count(), machine.transitions.length);
        assert.equal(await page.locator('.transition-io-node[data-io-kind="input"]').count(), 0);
        assert.equal(await page.locator('.transition-io-node[data-io-kind="output"]').count(), 0);
        assert.equal(await page.locator(".transition-detail").count(), machine.transitions.length);
        assert.equal(await page.locator(".state-transition-path").count(), machine.transitions.length);

        const combinedValues = await page.locator('.transition-io-node[data-io-kind="io"]').evaluateAll(elements => elements.map(element => {
          const cluster = element.closest(".transition-io-cluster");
          return {
            id: cluster?.dataset.transitionId || "",
            value: element.querySelector(".transition-io-value")?.textContent || "",
            input: cluster?.dataset.inputValue || "",
            action: cluster?.dataset.actionValue || "",
          };
        }));
        assert(combinedValues.every(({value}) => value.trim().length > 0));
        for (const rendered of combinedValues) {
          const transition = machine.transitions.find(item => item.id === rendered.id);
          assert(transition, `${testCase.slug}/${expected.name}: missing transition ${rendered.id}`);
          const expectedAction = actionDisplay(transition);
          assert.equal(
            rendered.action,
            expectedAction,
            `${testCase.slug}/${expected.name}/${rendered.id}: DOM Action differs from StateTransitionIR`,
          );
          assert.notEqual(
            rendered.action,
            String(transition.target_state || ""),
            `${testCase.slug}/${expected.name}/${rendered.id}: Target State leaked into Action`,
          );
          if (expectedAction) {
            assert(
              rendered.value.includes(` ➞ ${expectedAction}`),
              `${testCase.slug}/${expected.name}/${rendered.id}: Action is not rendered`,
            );
            assert(!rendered.value.includes(" / "));
          } else {
            assert(
              !rendered.value.includes(" ➞ "),
              `${testCase.slug}/${expected.name}/${rendered.id}: transition without Action rendered an arrow Action`,
            );
            assert(!rendered.value.includes(" / "));
          }
        }

        if (expected.requireInputAction) {
          const semanticPairs = combinedValues.filter(({input, action, value}) => (
            input.trim().length > 0
            && action.trim().length > 0
            && value.includes(" ➞ ")
          ));
          assert(
            semanticPairs.length > 0,
            `${testCase.slug}/${expected.name}: README candidate has no Input ➞ Action transition`,
          );
          for (const rendered of semanticPairs) {
            const transition = machine.transitions.find(item => item.id === rendered.id);
            assert(transition, `${testCase.slug}/${expected.name}: missing transition ${rendered.id}`);
            assert.notEqual(
              rendered.input,
              rendered.action,
              `${testCase.slug}/${expected.name}/${rendered.id}: intermediate Action repeated as Input`,
            );
            assert.notEqual(
              rendered.action,
              String(transition.target_state || ""),
              `${testCase.slug}/${expected.name}/${rendered.id}: Target State repeated as Action`,
            );
            assert.equal(
              transition.trigger?.provenance,
              "decision-output-preimage",
              `${testCase.slug}/${expected.name}/${rendered.id}: Input lacks proven decision preimage`,
            );
            assert(
              rendered.value.includes(` ➞ ${rendered.action}`),
              `${testCase.slug}/${expected.name}/${rendered.id}: rendered join is not Input ➞ Action`,
            );
          }
        }

        if (expected.provisionalTriggers !== undefined) {
          assert.equal(
            await page.locator(".transition-io-cluster.provisional-trigger").count(),
            expected.provisionalTriggers,
          );
        }

        const visibleLegacyLabels = await page.locator(".transition-label").evaluateAll(elements => elements.filter(element => {
          const style = getComputedStyle(element);
          return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0;
        }).length);
        assert.equal(visibleLegacyLabels, 0);
        await assertDiagramGeometry(page);

        await page.screenshot({
          path: path.join(outputDirectory, `${testCase.slug}-${expected.name.toLowerCase()}.png`),
          fullPage: true,
        });
      }
      await page.close();
    } finally {
      await stopProcess(child);
      port += 1;
    }
  }
} finally {
  await browser.close();
}

console.log("verified compiler-derived state diagrams with compact input-arrow-Action labels");
