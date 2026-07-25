import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const port = 8886;
const url = `http://127.0.0.1:${port}`;
const outputDirectory = path.resolve("build/code-derived-system-io");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(child, logs) {
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
const child = spawn("python3", ["glyph.py", "examples/acceptance/door_controller.glyph"], {
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
  const apiState = await waitForServer(child, logs);
  const system = apiState.views.io.systems.find(item => item.name === "DoorController");
  assert(system, "DoorController system is missing");
  assert.equal(system.kind, "code-derived-system");
  assert.equal(system.entry, "control");

  const nodes = new Map(system.nodes.map(node => [node.name, node]));
  assert.equal(nodes.get("sensor")?.kind, "external");
  assert.equal(nodes.get("sensor")?.declared_io, true);
  assert.equal(nodes.get("sensor")?.output, "Input");
  assert.equal(nodes.get("control")?.kind, "function");
  assert.equal(nodes.get("lock")?.kind, "effect");
  assert.equal(nodes.get("alarm")?.kind, "effect");
  assert.equal(system.nodes.some(node => node.declared_io === false), false);

  const names = new Map(system.nodes.map(node => [node.id, node.name]));
  const edges = new Set(system.edges.map(edge => `${names.get(edge.source_id)}->${names.get(edge.target_id)}`));
  for (const expected of [
    "control->apply",
    "control->step",
    "control->sensor",
    "step->decide",
    "decide->authenticate",
    "apply->lock",
    "apply->alarm",
  ]) {
    assert(edges.has(expected), `missing code-derived edge ${expected}`);
  }

  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.waitForFunction(() => {
    const selected = document.querySelector("#system-select")?.selectedOptions?.[0]?.textContent;
    return selected === "DoorController"
      && document.body.textContent?.includes("Derived from code")
      && document.body.textContent?.includes("Entry: control");
  });

  const result = await page.evaluate(() => ({
    note: document.querySelector(".view-controls .note")?.textContent,
    edgeLabels: [...document.querySelectorAll(".canvas-shell .edge-label")].map(item => item.textContent?.trim()),
    nodes: [...document.querySelectorAll(".graph-node")].map(item => ({
      name: item.querySelector(".node-name")?.textContent?.trim(),
      kind: item.querySelector(".node-kind")?.textContent?.trim(),
      input: item.querySelector(".port-group:first-child")?.textContent?.trim(),
      output: item.querySelector(".port-group:last-child")?.textContent?.trim(),
    })),
  }));

  assert(result.note?.includes("実際の関数呼出しを追跡"));
  assert(result.edgeLabels.length > 0);
  assert(result.edgeLabels.every(label => label === "calls"));
  assert.equal(result.nodes.some(node => node.input?.includes("undeclared") || node.output?.includes("undeclared")), false);
  assert(result.nodes.some(node => node.name === "sensor" && node.kind?.startsWith("external")));

  await page.screenshot({
    path: path.join(outputDirectory, "door-controller-code-derived-io.png"),
    fullPage: true,
  });
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified code-derived system topology, explicit ext ports, and call-only edges");
