import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const source = "examples/acceptance/motor_safety.glyph";
const outputDirectory = path.resolve("build/direct-io");
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
        if (state.status === "ready") return state;
      }
    } catch {
      // Server is still starting.
    }
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

const logs = [];
const port = 8965;
const child = spawn("python3", ["glyph.py", source], {
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

const browser = await chromium.launch({ headless: true });
try {
  const url = `http://127.0.0.1:${port}`;
  await waitForServer(url, child, logs);
  const page = await browser.newPage({
    viewport: { width: 1800, height: 1100 },
    deviceScaleFactor: 1,
  });
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.waitForFunction(() => (
    document.querySelector(".graph-node")?.closest(".graph-stage")?.dataset.ioContractReady === "true"
  ));

  const stage = page.locator(".graph-node").first().locator("xpath=ancestor::div[contains(@class,'graph-stage')]");
  assert.equal(await stage.locator(".edge-label").count(), 0, "I/O edges must not carry abstract labels");
  assert.equal(await page.getByText("connects", { exact: true }).count(), 0, "generic connects label must be absent");
  assert.equal(await page.getByText(/^T\d+$/).count(), 0, "I/O must not use transition-style reference IDs");

  const decide = page.locator(".graph-node").filter({ has: page.locator(".node-name", { hasText: "decide" }) });
  assert.equal(await decide.count(), 1, "decide component is missing");
  const decideRows = await decide.locator(".port").allTextContents();
  assert(decideRows.some(text => text.includes("IN") && text.includes("input: Input")), "decide input contract is not written directly");
  assert(decideRows.some(text => text.includes("OUT") && text.includes("Command")), "decide output contract is not written directly");

  const step = page.locator(".graph-node").filter({ has: page.locator(".node-name", { hasText: "step" }) });
  const stepRows = await step.locator(".port").allTextContents();
  assert(stepRows.some(text => text.includes("IN") && text.includes("state: MotorState")), "step state input is missing");
  assert(stepRows.some(text => text.includes("IN") && text.includes("input: Input")), "step input is missing");
  assert(stepRows.some(text => text.includes("OUT") && text.includes("MotorState")), "step output is missing");

  const whiteSpace = await decide.locator(".port-text").first().evaluate(element => getComputedStyle(element).whiteSpace);
  const overflow = await decide.locator(".port-text").first().evaluate(element => getComputedStyle(element).overflow);
  assert.equal(whiteSpace, "normal", "I/O contract text must wrap instead of truncating");
  assert.equal(overflow, "visible", "I/O contract text must remain fully visible");

  await page.screenshot({
    path: path.join(outputDirectory, "motor-safety-direct-io.png"),
    fullPage: true,
  });
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified direct, unlabeled I/O rendering");
