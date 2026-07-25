import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const port = 8886;
const url = `http://127.0.0.1:${port}`;
const outputDirectory = path.resolve("build/checked-system-context-io");
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
  assert.equal(system.kind, "checked-system-context");
  assert.equal(system.entry, "control");

  assert.deepEqual(
    new Set(system.ports.map(port => `${port.direction}:${port.name}:${port.type}`)),
    new Set([
      "input:state:DoorState",
      "input:sensor:Input",
      "output:receipt:Receipt",
    ]),
  );

  const nodes = new Map(system.nodes.map(node => [node.name, node]));
  assert.deepEqual(
    new Set(nodes.keys()),
    new Set(["state", "sensor", "control", "receipt", "lock", "alarm"]),
  );
  assert.equal(nodes.get("state")?.kind, "input");
  assert.equal(nodes.get("sensor")?.kind, "external");
  assert.equal(nodes.get("sensor")?.declared_io, true);
  assert.equal(nodes.get("sensor")?.port_type, "Input");
  assert.equal(nodes.get("receipt")?.kind, "output");
  assert.equal(nodes.get("receipt")?.port_type, "Receipt");
  assert.equal(nodes.get("control")?.kind, "function");
  assert.equal(nodes.get("lock")?.kind, "effect");
  assert.equal(nodes.get("alarm")?.kind, "effect");

  const names = new Map(system.nodes.map(node => [node.id, node.name]));
  const edges = new Set(
    system.edges.map(
      edge => `${names.get(edge.source_id)}->${names.get(edge.target_id)}:${edge.label}`,
    ),
  );
  for (const expected of [
    "state->control:data",
    "sensor->control:data",
    "control->receipt:returns",
    "control->lock:effect",
    "control->alarm:effect",
  ]) {
    assert(edges.has(expected), `missing checked boundary edge ${expected}`);
  }
  assert.deepEqual(
    new Set(system.evidence.map(item => item.kind)),
    new Set(["entry-parameter", "external-input-read", "return-type", "effect-reachability"]),
  );

  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.waitForFunction(() => {
    const active = document.querySelector(".tab.active")?.dataset.tab;
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return active === "state" && stage?.dataset.renderStable === "true";
  });
  assert.equal(await page.locator(".tab.active").getAttribute("data-tab"), "state");

  await page.locator('.tab[data-tab="io"]').click();
  await page.waitForFunction(() => {
    const selected = document.querySelector("#system-select")?.selectedOptions?.[0]?.textContent;
    return document.querySelector(".tab.active")?.dataset.tab === "io"
      && selected === "DoorController"
      && document.body.textContent?.includes("Checked system context")
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

  assert(result.note?.includes("call graphとは別のview"));
  assert.deepEqual(new Set(result.edgeLabels), new Set(["data", "returns", "effect"]));
  assert.equal(
    result.nodes.some(node => node.input?.includes("undeclared") || node.output?.includes("undeclared")),
    false,
  );
  assert(result.nodes.some(node => node.name === "sensor" && node.kind?.startsWith("external")));

  await page.screenshot({
    path: path.join(outputDirectory, "door-controller-checked-system-context.png"),
    fullPage: true,
  });
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified state-first startup and checked System Context boundaries");
