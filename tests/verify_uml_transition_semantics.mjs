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
  },
  {
    slug: "traffic-uml",
    file: "examples/state_diagrams/traffic_light.glyph",
    machine: "Traffic",
    labels: ["[input.tick]", "[input.fault]"],
    failureLabels: ["[input.fault]"],
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
          return selected === machineName && stage?.dataset.umlTransitionReady === "true";
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

console.log(`verified ${cases.length} UML event/guard/action diagrams`);
