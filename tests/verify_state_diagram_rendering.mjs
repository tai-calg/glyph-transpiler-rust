import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const cases = [
  {
    slug: "motor-safety",
    file: "examples/acceptance/motor_safety.glyph",
    machines: [
      {
        name: "Motor",
        states: ["Stopped", "Running", "Faulted"],
        warnings: ["state-independent-transition", "unreachable-branch", "unreachable-state"],
      },
    ],
  },
  {
    slug: "traffic-light",
    file: "examples/state_diagrams/traffic_light.glyph",
    machines: [
      {
        name: "Traffic",
        states: ["Red", "Green", "Yellow", "TrafficFault"],
        warnings: [],
        compact: true,
        labels: [
          "input.fault",
          "state.mode==Red&input.tick",
          "state.mode==Green&input.tick",
          "state.mode==Yellow&input.tick",
        ],
      },
    ],
  },
  {
    slug: "session-protocol",
    file: "examples/state_diagrams/session_protocol.glyph",
    machines: [
      {
        name: "Session",
        states: ["SessionIdle", "SessionConnecting", "SessionReady", "SessionFailed"],
        warnings: [],
        compact: true,
        labels: [
          "state.phase==SessionIdle&event==SessionStart",
          "state.phase==SessionConnecting&event==SessionAccept",
          "state.phase==SessionConnecting&event==SessionReject",
          "state.phase==SessionReady&event==SessionReset",
          "state.phase==SessionFailed&event==SessionReset",
        ],
      },
    ],
  },
  {
    slug: "dual-machines",
    file: "examples/state_diagrams/dual_machines.glyph",
    machines: [
      {
        name: "Door",
        states: ["DoorClosed", "DoorOpen", "DoorJammed"],
        warnings: ["unreachable-state"],
        compact: true,
        labels: [
          "state.mode==DoorClosed&event==DoorOpenRequest",
          "state.mode==DoorOpen&event==DoorCloseRequest",
        ],
      },
      {
        name: "Power",
        states: ["PowerOff", "PowerOn", "PowerFault"],
        warnings: [],
        compact: true,
        labels: [
          "event==PowerTrip",
          "state.mode==PowerOff&event==PowerStart",
          "state.mode==PowerOn&event==PowerStop",
        ],
      },
    ],
  },
];

const outputDirectory = path.resolve("build/state-diagram-regression");
await fs.mkdir(outputDirectory, { recursive: true });

function sorted(values) {
  return [...values].sort((left, right) => left.localeCompare(right));
}

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`Glyph diagram process exited early (${child.exitCode})\n${logs.join("")}`);
    }
    try {
      const response = await fetch(`${url}/api/state`);
      if (response.ok) {
        const state = await response.json();
        if (state.status === "ready") return state;
      }
    } catch {
      // Server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Glyph diagram server did not become ready\n${logs.join("")}`);
}

async function stopProcess(child) {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => child.once("exit", resolve)),
    new Promise((resolve) => setTimeout(resolve, 1500)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

async function assertDiagramGeometry(page) {
  const result = await page.evaluate(() => {
    const stage = document.querySelector(".graph-stage");
    if (!stage) return { error: "graph stage is missing" };
    const stageRect = stage.getBoundingClientRect();
    const nodes = [...document.querySelectorAll(".state-node")].map((element) => ({
      kind: "state",
      name: element.textContent?.trim(),
      rect: element.getBoundingClientRect(),
    }));
    const labels = [...document.querySelectorAll(".edge-label.transition-label")].map((element) => ({
      kind: "label",
      name: element.dataset.transitionId,
      rect: element.getBoundingClientRect(),
    }));
    const outside = [...nodes, ...labels].filter(({rect}) => (
      rect.left < stageRect.left - 1 ||
      rect.top < stageRect.top - 1 ||
      rect.right > stageRect.right + 1 ||
      rect.bottom > stageRect.bottom + 1
    ));
    const intersects = (left, right) => !(
      left.right <= right.left + 1 ||
      right.right <= left.left + 1 ||
      left.bottom <= right.top + 1 ||
      right.bottom <= left.top + 1
    );
    const overlaps = [];
    for (let index = 0; index < labels.length; index += 1) {
      for (let other = index + 1; other < labels.length; other += 1) {
        if (intersects(labels[index].rect, labels[other].rect)) {
          overlaps.push(`${labels[index].name}/${labels[other].name}`);
        }
      }
      for (const node of nodes) {
        if (intersects(labels[index].rect, node.rect)) {
          overlaps.push(`${labels[index].name}/${node.name}`);
        }
      }
    }
    return {outside: outside.map(item => `${item.kind}:${item.name}`), overlaps};
  });
  assert.equal(result.error, undefined, result.error);
  assert.deepEqual(result.outside, [], `items outside graph stage: ${JSON.stringify(result.outside)}`);
  assert.deepEqual(result.overlaps, [], `transition label overlap: ${JSON.stringify(result.overlaps)}`);
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
    child.stdout.on("data", (chunk) => logs.push(chunk.toString()));
    child.stderr.on("data", (chunk) => logs.push(chunk.toString()));

    const url = `http://127.0.0.1:${port}`;
    try {
      const apiState = await waitForServer(url, child, logs);
      assert.equal(apiState.views.schema, "glyph.io-state-views");
      assert.equal(apiState.views.version, 2);
      assert.equal(apiState.views.state.machines.length, testCase.machines.length);

      const page = await browser.newPage({
        viewport: { width: 1800, height: 1100 },
        deviceScaleFactor: 1,
      });
      await page.goto(url, { waitUntil: "networkidle" });
      await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
      await page.click('button[data-tab="state"]');

      const options = await page.locator("#machine-select option").allTextContents();
      assert.deepEqual(sorted(options), sorted(testCase.machines.map((machine) => machine.name)));

      for (const expected of testCase.machines) {
        const machine = apiState.views.state.machines.find((item) => item.name === expected.name);
        assert.ok(machine, `${testCase.slug}/${expected.name}: API machine missing`);
        const transitionCount = machine.transitions.length;

        if (testCase.machines.length > 1) {
          await page.selectOption("#machine-select", { label: expected.name });
        }
        await page.waitForFunction(
          ({machineName, transitionCount}) => {
            const selected = document.querySelector("#machine-select")?.selectedOptions?.[0]?.textContent;
            const stage = document.querySelector(".graph-stage");
            return selected === machineName
              && stage?.dataset.labelLayoutReady === "true"
              && stage?.dataset.initialRouteReady === "true"
              && stage.querySelectorAll(".edge-label.transition-label").length === transitionCount;
          },
          {machineName: expected.name, transitionCount},
        );

        const stateNames = await page.locator(".state-name").allTextContents();
        assert.deepEqual(sorted(stateNames), sorted(expected.states), `${testCase.slug}/${expected.name}: states`);
        assert.equal(await page.locator(".initial-dot").count(), 1, `${testCase.slug}/${expected.name}: initial marker`);
        assert.equal(await page.locator(".initial-transition-path").count(), 1, `${testCase.slug}/${expected.name}: initial path`);
        assert.equal(await page.getByText("Any state", { exact: true }).count(), 0);
        assert.equal(await page.locator('.state-name:has-text("*")').count(), 0);

        const warningCodes = await page.locator(".analysis-code").allTextContents();
        assert.deepEqual(sorted(warningCodes), sorted(expected.warnings), `${testCase.slug}/${expected.name}: warnings`);

        assert.equal(
          await page.locator(".edge-label.transition-label").count(),
          transitionCount,
          `${testCase.slug}/${expected.name}: transition labels`,
        );
        assert.equal(
          await page.locator(".transition-detail").count(),
          transitionCount,
          `${testCase.slug}/${expected.name}: transition details`,
        );
        assert.equal(
          await page.locator(".state-transition-path").count(),
          transitionCount,
          `${testCase.slug}/${expected.name}: transition paths`,
        );

        const labelIds = await page.locator(".edge-label.transition-label").evaluateAll(
          elements => elements.map(element => element.dataset.transitionId),
        );
        const detailIds = await page.locator(".transition-detail").evaluateAll(
          elements => elements.map(element => element.dataset.transitionId),
        );
        assert.deepEqual(sorted(labelIds), sorted(detailIds));

        const fullLabels = await page.locator(".transition-detail-condition").allTextContents();
        for (const expectedLabel of expected.labels ?? []) {
          assert(fullLabels.includes(expectedLabel), `${testCase.slug}/${expected.name}: missing full transition label ${expectedLabel}`);
        }
        if (expected.compact) {
          assert(
            await page.locator(".edge-label.transition-label.compact").count() > 0,
            `${testCase.slug}/${expected.name}: expected compact labels`,
          );
        }

        await assertDiagramGeometry(page);
        await page.screenshot({
          path: path.join(outputDirectory, `${testCase.slug}-${expected.name.toLowerCase()}.png`),
          fullPage: true,
        });
      }
      await page.close();
    } finally {
      await stopProcess(child);
    }
    port += 1;
  }
} finally {
  await browser.close();
}

console.log(`verified ${cases.length} Glyph files and ${cases.reduce((sum, item) => sum + item.machines.length, 0)} collision-free state-machine renderings`);
