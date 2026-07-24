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
        warnings: [],
      },
    ],
  },
  {
    slug: "traffic-light",
    file: "examples/state_diagrams/traffic_light.glyph",
    machines: [
      {
        name: "Traffic",
        states: ["Red", "Green", "Yellow", "Fault"],
        warnings: [],
      },
    ],
  },
  {
    slug: "session-protocol",
    file: "examples/state_diagrams/session_protocol.glyph",
    machines: [
      {
        name: "Session",
        states: ["Idle", "Pending", "Active", "Rejected"],
        warnings: [],
      },
    ],
  },
  {
    slug: "dual-machines",
    file: "examples/state_diagrams/dual_machines.glyph",
    machines: [
      {
        name: "Door",
        states: ["Closed", "Open", "Jammed"],
        warnings: [],
      },
      {
        name: "Power",
        states: ["Off", "On", "Fault"],
        warnings: [],
      },
    ],
  },
];

const outputDirectory = path.resolve("build/state-diagram-regression");
await fs.mkdir(outputDirectory, { recursive: true });

const sorted = values => [...values].sort((left, right) => left.localeCompare(right));

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`Glyph process exited early (${child.exitCode})\n${logs.join("")}`);
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
    const sample = (svgPath, step = 3) => {
      const length = svgPath.getTotalLength();
      const values = [];
      for (let offset = 0; offset < length; offset += step) {
        values.push(point(svgPath.getPointAtLength(offset)));
      }
      values.push(point(svgPath.getPointAtLength(length)));
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
  let port = 8850;
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
              && stage.querySelector(":scope > svg.edge-svg > path.initial-transition-path")
              && stage.querySelector(".initial-dot")
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
        assert.equal(new Set(labelIds).size, transitionCount, `${testCase.slug}/${expected.name}: duplicate transition ids`);
        assert(labelIds.every(Boolean), `${testCase.slug}/${expected.name}: missing transition id`);

        await assertInitialRouteClear(page, expected.name);
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

console.log(`verified ${cases.length} state diagram examples`);
