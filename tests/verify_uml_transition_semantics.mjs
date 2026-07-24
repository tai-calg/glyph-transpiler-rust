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
      "SessionStart➡︎—",
      "SessionAccept➡︎—",
      "SessionReject➡︎—",
      "SessionReset➡︎—",
    ],
  },
  {
    slug: "traffic-uml",
    file: "examples/state_diagrams/traffic_light.glyph",
    machine: "Traffic",
    labels: ["[input.tick]", "[input.fault]"],
    failureLabels: ["[input.fault]"],
    compactLabels: ["[input.tick]➡︎—", "[input.fault]➡︎—"],
  },
  {
    slug: "effect-failure-uml",
    file: "examples/state_diagrams/effect_failure.glyph",
    machine: "Pump",
    labels: [
      "PumpStart / write_pump(true)",
      "PumpStop / write_pump(false)",
      "PumpStart / write_pump(true) | WriteError",
      "PumpStop / write_pump(false) | WriteError",
    ],
    failureLabels: [
      "PumpStart / write_pump(true) | WriteError",
      "PumpStop / write_pump(false) | WriteError",
    ],
    compactLabels: [
      "PumpStart➡︎write_pump(true)",
      "PumpStop➡︎write_pump(false)",
      "PumpStart➡︎write_pump(true) | WriteError",
      "PumpStop➡︎write_pump(false) | WriteError",
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
      "ConveyorStart [input.clear] / set_conveyor(input.speed) | DriveError",
    ],
    failureLabels: [
      "ConveyorStart [input.clear] / set_conveyor(input.speed) | DriveError",
      "ConveyorStop / set_conveyor(0.0) | DriveError",
      "ConveyorReset [input.clear] / set_conveyor(0.0) | DriveError",
    ],
    compactLabels: [
      "ConveyorStart [input.clear]➡︎set_conveyor(input.speed)",
      "ConveyorStop➡︎set_conveyor(0.0)",
      "ConveyorReset [input.clear]➡︎set_conveyor(0.0)",
      "ConveyorStart [input.clear]➡︎set_conveyor(input.speed) | DriveError",
    ],
  },
  {
    slug: "valve-nested-action-uml",
    file: "examples/state_diagrams/valve_nested_effect.glyph",
    machine: "Valve",
    labels: [
      "ValveOpenRequest / write_valve(true)",
      "ValveCloseRequest / write_valve(false)",
      "ValveOpenRequest / write_valve(true) | ValveError",
      "ValveCloseRequest / write_valve(false) | ValveError",
    ],
    failureLabels: [
      "ValveOpenRequest / write_valve(true) | ValveError",
      "ValveCloseRequest / write_valve(false) | ValveError",
    ],
    compactLabels: [
      "ValveOpenRequest➡︎write_valve(true)",
      "ValveCloseRequest➡︎write_valve(false)",
      "ValveOpenRequest➡︎write_valve(true) | ValveError",
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

async function assertInitialRouteClear(page, machineName) {
  const result = await page.evaluate(() => {
    const svg = document.querySelector(".graph-stage > svg.edge-svg");
    const initial = svg?.querySelector(":scope > path.initial-transition-path");
    const normals = [...(svg?.querySelectorAll(":scope > path.state-transition-path") || [])];
    if (!initial) return {error: "initial transition path is missing"};

    const point = value => ({x: value.x, y: value.y});
    const distance = (left, right) => Math.hypot(left.x - right.x, left.y - right.y);
    const sample = (path, step = 3) => {
      const length = path.getTotalLength();
      const values = [];
      for (let offset = 0; offset < length; offset += step) {
        values.push(point(path.getPointAtLength(offset)));
      }
      values.push(point(path.getPointAtLength(length)));
      return values;
    };
    const orientation = (a, b, c) => (
      (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
    );
    const between = (value, first, second) => (
      value >= Math.min(first, second) - .001 && value <= Math.max(first, second) + .001
    );
    const intersects = (a, b, c, d) => {
      const abC = orientation(a, b, c);
      const abD = orientation(a, b, d);
      const cdA = orientation(c, d, a);
      const cdB = orientation(c, d, b);
      if (((abC > 0 && abD < 0) || (abC < 0 && abD > 0))
        && ((cdA > 0 && cdB < 0) || (cdA < 0 && cdB > 0))) return true;
      const collinear = (value, p, q, r) => Math.abs(value) < .001
        && between(r.x, p.x, q.x) && between(r.y, p.y, q.y);
      return collinear(abC, a, b, c)
        || collinear(abD, a, b, d)
        || collinear(cdA, c, d, a)
        || collinear(cdB, c, d, b);
    };

    const initialPoints = sample(initial);
    let crossings = 0;
    let minimum = Number.POSITIVE_INFINITY;
    for (const normal of normals) {
      const normalPoints = sample(normal);
      for (let left = 1; left < initialPoints.length; left += 1) {
        for (let right = 1; right < normalPoints.length; right += 1) {
          if (intersects(
            initialPoints[left - 1], initialPoints[left],
            normalPoints[right - 1], normalPoints[right],
          )) crossings += 1;
        }
      }
      for (const left of initialPoints) {
        for (const right of normalPoints) minimum = Math.min(minimum, distance(left, right));
      }
    }
    if (!normals.length) minimum = 999;
    return {
      crossings,
      minimum,
      declaredCrossings: Number(initial.dataset.routeCrossings),
      declaredClearance: Number(initial.dataset.routeClearance),
      side: initial.dataset.routeSide,
    };
  });

  assert.equal(result.error, undefined, `${machineName}: ${result.error}`);
  assert.equal(result.crossings, 0, `${machineName}: initial route crosses normal transitions`);
  assert.equal(result.declaredCrossings, 0, `${machineName}: router reported a crossing`);
  assert(result.minimum >= 5, `${machineName}: initial route clearance is ${result.minimum}px`);
  assert(result.declaredClearance >= 5, `${machineName}: declared clearance is ${result.declaredClearance}px`);
  assert(result.side, `${machineName}: initial route side is missing`);
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
            && stage?.dataset.transitionInputActionLabelsReady === "true"
            && stage?.dataset.failureResultNotationReady === "true"
            && stage?.dataset.initialRouteReady === "true";
        },
        testCase.machine,
      );

      const semanticLabels = await page.locator(".transition-detail-uml").allTextContents();
      const compactLabels = await page.locator(".edge-label.transition-label.compact").allTextContents();
      const detailIds = await page.locator(".transition-detail-id.input-action-label").allTextContents();
      const visibleLabels = [...semanticLabels, ...compactLabels, ...detailIds];

      for (const label of testCase.labels) {
        assert(
          semanticLabels.some(item => item.includes(label)),
          `${testCase.machine}: missing semantic label ${label}`,
        );
      }
      const failures = await page.locator(
        ".transition-detail.failure-transition .transition-detail-uml",
      ).allTextContents();
      for (const label of testCase.failureLabels) {
        assert(
          failures.some(item => item.includes(label)),
          `${testCase.machine}: missing failure transition ${label}`,
        );
      }
      for (const expected of testCase.compactLabels) {
        assert(
          compactLabels.some(label => label.includes(expected)),
          `${testCase.machine}: missing compact label ${expected}`,
        );
      }

      assert(
        visibleLabels.every(label => !/ ! (WriteError|DriveError|ValveError)/.test(label)),
        `${testCase.machine}: old effect-sigil failure notation remains visible`,
      );
      assert(
        compactLabels.every(label => !/^T\d+$/.test(label.trim())),
        `${testCase.machine}: internal transition IDs are visible`,
      );
      assert.equal(
        await page.locator(".state-transition-path.failure-transition").count(),
        machine.transitions.filter(item => item.outcome === "failure").length,
      );

      await assertInitialRouteClear(page, testCase.machine);
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

console.log(`verified ${cases.length} UML diagrams with Glyph pipe failure notation`);
