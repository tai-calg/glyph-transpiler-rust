import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const cases = [
  {
    slug: "door-lock-pipe-failure",
    file: "examples/state_diagrams/door_lock_effect.glyph",
    machine: "DoorLock",
    expected: [
      "DoorUnlockRequest [input.authorized]",
      "DoorLockRequest",
      "DoorReset",
      "DoorUnlockRequest [input.authorized] | DoorWriteError",
      "DoorLockRequest | DoorWriteError",
      "DoorReset | DoorWriteError",
    ],
    expectedEffects: ["write_lock(true)", "write_lock(false)"],
    failureType: "DoorWriteError",
  },
  {
    slug: "cooling-fan-pipe-failure",
    file: "examples/state_diagrams/cooling_fan_effect.glyph",
    machine: "CoolingFan",
    expected: [
      "? input.overheat",
      "? input.enable",
      "? !input.enable",
      "? input.overheat | FanWriteError",
      "? input.enable | FanWriteError",
      "? !input.enable | FanWriteError",
    ],
    expectedEffects: ["write_fan(0.0)", "write_fan(input.speed)"],
    failureType: "FanWriteError",
  },
];

const outputDirectory = path.resolve("build/additional-failure-notation");
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
        if (state.status === "ready" && state.views?.transition_semantics_version === 2) {
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

function actionDisplay(transition) {
  const raw = transition?.action;
  if (typeof raw === "string") return raw.trim();
  return String(raw?.display || raw?.expression || "").trim();
}

const browser = await chromium.launch({ headless: true });
try {
  let port = 8965;
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
      assert.equal(state.views.state_transition_ir.version, 4);
      const machine = state.views.state.machines.find(item => item.name === testCase.machine);
      assert.ok(machine, `${testCase.machine}: machine missing`);
      assert(
        machine.transitions.some(item => item.synthesized_failure && item.failure_type === testCase.failureType),
        `${testCase.machine}: synthesized failure transition missing`,
      );

      for (const effect of testCase.expectedEffects) {
        assert(
          machine.transitions.some(transition => (
            transition.effect_invocations || []
          ).some(invocation => invocation.expression === effect)),
          `${testCase.machine}: Effect invocation missing from IR: ${effect}`,
        );
        assert(
          machine.transitions.every(transition => !actionDisplay(transition).includes(effect)),
          `${testCase.machine}: Effect invocation leaked into Action: ${effect}`,
        );
      }

      await fs.writeFile(
        path.join(outputDirectory, `${testCase.slug}.json`),
        JSON.stringify(machine, null, 2),
        "utf8",
      );

      const page = await browser.newPage({
        viewport: { width: 1800, height: 1250 },
        deviceScaleFactor: 1,
      });
      await page.goto(url, { waitUntil: "domcontentloaded" });
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

      const semantic = await page.locator(".transition-detail-uml").allTextContents();
      const compact = await page.locator(".edge-label.transition-label.compact").allTextContents();
      const summaries = await page.locator(".transition-detail-id.input-action-label").allTextContents();
      const visible = [...semantic, ...compact, ...summaries];

      for (const expected of testCase.expected) {
        assert(
          semantic.some(label => label.includes(expected)),
          `${testCase.machine}: missing ${expected}`,
        );
      }
      for (const effect of testCase.expectedEffects) {
        assert(
          visible.every(label => !label.includes(`➡︎${effect}`) && !label.includes(` / ${effect}`)),
          `${testCase.machine}: Effect is visible in Action position: ${effect}`,
        );
      }
      assert(
        visible.every(label => !label.includes("➡︎—")),
        `${testCase.machine}: missing Action is rendered as a placeholder Action`,
      );
      assert(
        visible.every(label => !label.includes(` ! ${testCase.failureType}`)),
        `${testCase.machine}: old ! failure notation remains visible`,
      );
      assert(
        visible.some(label => label.includes(` | ${testCase.failureType}`)),
        `${testCase.machine}: pipe failure notation is not visible`,
      );
      assert.equal(
        await page.locator(".state-transition-path.failure-transition").count(),
        machine.transitions.filter(item => item.outcome === "failure").length,
        `${testCase.machine}: failure-edge count mismatch`,
      );
      assert.equal(
        await page.locator(".initial-transition-path").count(),
        1,
        `${testCase.machine}: initial transition missing`,
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

console.log(`verified ${cases.length} additional diagrams with separate Action, Effect, and failure notation`);
