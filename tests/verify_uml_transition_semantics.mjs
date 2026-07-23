import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const cases = [
  {
    slug: "session-uml",
    file: "examples/state_diagrams/session_protocol.glyph",
    machine: "Session",
    labels: ["SessionStart", "SessionAccept", "SessionReject", "SessionReset"],
    failureLabels: ["SessionReject"],
    compactLabels: [
      "SessionStart→—",
      "SessionAccept→—",
      "SessionReject→—",
      "SessionReset→—",
    ],
  },
  {
    slug: "traffic-uml",
    file: "examples/state_diagrams/traffic_light.glyph",
    machine: "Traffic",
    labels: ["[input.tick]", "[input.fault]"],
    failureLabels: ["[input.fault]"],
    compactLabels: ["[input.tick]→—", "[input.fault]→—"],
  },
  {
    slug: "effect-failure-uml",
    file: "examples/state_diagrams/effect_failure.glyph",
    machine: "Pump",
    labels: [
      "PumpStart / write_pump(true)",
      "PumpStop / write_pump(false)",
      "PumpStart / write_pump(true) ! WriteError",
      "PumpStop / write_pump(false) ! WriteError",
    ],
    failureLabels: [
      "PumpStart / write_pump(true) ! WriteError",
      "PumpStop / write_pump(false) ! WriteError",
    ],
    compactLabels: [
      "PumpStart→write_pump(true)",
      "PumpStop→write_pump(false)",
      "PumpStart→write_pump(true) ! WriteError",
      "PumpStop→write_pump(false) ! WriteError",
    ],
  },
  {
    slug: "conveyor-action-uml",
    file: "examples/state_diagrams/conveyor_control.glyph",
    machine: "Conveyor",
    labels: [
      "ConveyorStart [input.clear] / set_conveyor(input.speed)",
      "ConveyorStop / set_conveyor(0.0)",
      "ConveyorReset [input.clear] / set_conveyor(0.0)",
      "ConveyorStart [input.clear] / set_conveyor(input.speed) ! DriveError",
    ],
    failureLabels: [
      "ConveyorStart [input.clear] / set_conveyor(input.speed) ! DriveError",
      "ConveyorStop / set_conveyor(0.0) ! DriveError",
      "ConveyorReset [input.clear] / set_conveyor(0.0) ! DriveError",
    ],
    compactLabels: [
      "ConveyorStart [input.clear]→set_conveyor(input.speed)",
      "ConveyorStop→set_conveyor(0.0)",
      "ConveyorReset [input.clear]→set_conveyor(0.0)",
    ],
  },
  {
    slug: "valve-nested-action-uml",
    file: "examples/state_diagrams/valve_nested_effect.glyph",
    machine: "Valve",
    labels: [
      "ValveOpenRequest / write_valve(true)",
      "ValveCloseRequest / write_valve(false)",
      "ValveOpenRequest / write_valve(true) ! ValveError",
      "ValveCloseRequest / write_valve(false) ! ValveError",
    ],
    failureLabels: [
      "ValveOpenRequest / write_valve(true) ! ValveError",
      "ValveCloseRequest / write_valve(false) ! ValveError",
    ],
    compactLabels: [
      "ValveOpenRequest→write_valve(true)",
      "ValveCloseRequest→write_valve(false)",
    ],
  },
];

const outputDirectory = path.resolve("build/uml-transition-semantics");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`Glyph process exited early (${child.exitCode})\n${logs.join("")}`);
    }
    try {
      const response = await fetch(`${url}/api/state`);
      if (response.ok) {
        const state = await response.json();
        if (state.status === "ready" && state.views?.transition_semantics_version === 1) {
          return state;
        }
      }
    } catch {
      // Server is still starting.
    }
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

const browser = await chromium.launch({ headless: true });
try {
  let port = 8865;
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
      const state = await waitForServer(url, child, logs);
      const machine = state.views.state.machines.find(item => item.name === testCase.machine);
      assert.ok(machine, `${testCase.machine}: machine missing`);
      assert.equal(machine.analysis.transition_semantics_version, 1);

      const page = await browser.newPage({
        viewport: { width: 1800, height: 1200 },
        deviceScaleFactor: 1,
      });
      await page.goto(url, { waitUntil: "networkidle" });
      await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
      await page.click('button[data-tab="state"]');
      await page.waitForFunction(
        machineName => {
          const selected = document.querySelector("#machine-select")?.selectedOptions?.[0]?.textContent;
          const stage = document.querySelector(".graph-stage");
          return selected === machineName
            && stage?.dataset.umlTransitionReady === "true"
            && stage?.dataset.transitionInputActionLabelsReady === "true";
        },
        testCase.machine,
      );

      const semanticLabels = await page.locator(".transition-detail-uml").allTextContents();
      for (const label of testCase.labels) {
        assert(
          semanticLabels.some(item => item.includes(label)),
          `${testCase.machine}: missing semantic label ${label}`,
        );
      }

      const failures = await page.locator(".transition-detail.failure-transition .transition-detail-uml").allTextContents();
      for (const label of testCase.failureLabels) {
        assert(
          failures.some(item => item.includes(label)),
          `${testCase.machine}: missing failure transition ${label}`,
        );
      }
      assert.equal(
        await page.locator(".state-transition-path.failure-transition").count(),
        machine.transitions.filter(item => item.outcome === "failure").length,
      );

      const compactLabels = await page.locator(".edge-label.transition-label.compact").allTextContents();
      assert(compactLabels.length > 0, `${testCase.machine}: compact labels are missing`);
      assert(
        compactLabels.every(label => !/^T\d+$/.test(label.trim())),
        `${testCase.machine}: internal T identifiers leaked into visible labels`,
      );
      for (const expected of testCase.compactLabels) {
        assert(
          compactLabels.some(label => label.includes(expected)),
          `${testCase.machine}: missing compact input→action label ${expected}`,
        );
      }

      const detailIds = await page.locator(".transition-detail-id.input-action-label").allTextContents();
      assert(
        detailIds.every(label => !/^T\d+$/.test(label.trim())),
        `${testCase.machine}: internal T identifiers leaked into transition details`,
      );
      const detailOverlaps = await page.locator(".transition-detail").evaluateAll(rows => rows.flatMap((row, index) => {
        const id = row.querySelector(".transition-detail-id")?.getBoundingClientRect();
        const route = row.querySelector(".transition-detail-route")?.getBoundingClientRect();
        if (!id || !route) return [];
        const verticalOverlap = id.top < route.bottom && route.top < id.bottom;
        return verticalOverlap && id.right > route.left + 1 ? [`row-${index + 1}`] : [];
      }));
      assert.deepEqual(
        detailOverlaps,
        [],
        `${testCase.machine}: input→action labels overlap transition routes`,
      );

      await page.screenshot({
        path: path.join(outputDirectory, `${testCase.slug}.png`),
        fullPage: true,
      });
      await page.close();
    } finally {
      await stopProcess(child);
    }
    port += 1;
  }
} finally {
  await browser.close();
}

console.log(`verified ${cases.length} UML diagrams with compact input→action labels`);
