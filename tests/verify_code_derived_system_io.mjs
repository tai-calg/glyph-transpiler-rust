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

async function waitForReadyStatus(page) {
  try {
    await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  } catch (error) {
    const state = await page.evaluate(() => ({
      status: document.querySelector("#status")?.textContent,
      diagnostics: document.querySelector("#diagnostics")?.textContent,
      bodyPrefix: document.body.textContent?.slice(0, 800),
    }));
    throw new Error(`diagram did not become ready: ${JSON.stringify(state)}\n${error.stack}`);
  }
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
  assert.equal(system.contract, "executable-function-boundary");
  assert.equal(system.entry, "control");
  assert.deepEqual(system.sources, ["sensor"]);
  assert.deepEqual(new Set(system.sinks), new Set(["lock", "alarm"]));
  assert.deepEqual(system.ports, []);

  const nodes = new Map(system.nodes.map(node => [node.name, node]));
  assert.deepEqual(
    new Set(nodes.keys()),
    new Set([
      "control",
      "sensor",
      "step",
      "decide",
      "authenticate",
      "apply",
      "lock",
      "alarm",
    ]),
  );
  assert.equal(nodes.get("control")?.kind, "function");
  assert.equal(nodes.get("control")?.boundary_role, "entry");
  assert.deepEqual(nodes.get("control")?.inputs, [{ name: "state", type: "DoorState" }]);
  assert.equal(nodes.get("control")?.output, "Receipt|ControlError");

  assert.equal(nodes.get("sensor")?.kind, "external");
  assert.equal(nodes.get("sensor")?.boundary_role, "source");
  assert.equal(nodes.get("sensor")?.output, "Input|ControlError");

  for (const name of ["lock", "alarm"]) {
    assert.equal(nodes.get(name)?.kind, "effect");
    assert.equal(nodes.get(name)?.boundary_role, "sink");
    assert.equal(nodes.get(name)?.output, "Receipt|ControlError");
  }
  for (const name of ["step", "decide", "authenticate", "apply"]) {
    assert.equal(nodes.get(name)?.boundary_role, "internal");
  }

  const names = new Map(system.nodes.map(node => [node.id, node.name]));
  const edges = new Set(
    system.edges.map(
      edge => `${names.get(edge.source_id)}->${names.get(edge.target_id)}:${edge.label}`,
    ),
  );
  for (const expected of [
    "control->sensor:calls",
    "control->step:calls",
    "control->apply:calls",
    "step->decide:calls",
    "decide->authenticate:calls",
    "apply->lock:calls",
    "apply->alarm:calls",
  ]) {
    assert(edges.has(expected), `missing executable call edge ${expected}`);
  }
  assert.deepEqual(new Set(system.evidence.map(item => item.kind)), new Set(["call"]));

  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  page.on("pageerror", error => console.error("diagram page error", error));
  page.on("console", message => {
    if (["error", "warning"].includes(message.type())) {
      console.error(`diagram console ${message.type()}: ${message.text()}`);
    }
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await waitForReadyStatus(page);
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
      && document.body.textContent?.includes("Executable System boundary")
      && document.body.textContent?.includes("Entry: control")
      && document.body.textContent?.includes("Sources: sensor")
      && document.body.textContent?.includes("Sinks:");
  });

  const result = await page.evaluate(() => ({
    note: document.querySelector(".view-controls .note")?.textContent,
    edgeLabels: [...document.querySelectorAll(".canvas-shell .edge-label")].map(item => item.textContent?.trim()),
    nodes: [...document.querySelectorAll(".graph-node")].map(item => ({
      name: item.querySelector(".node-name")?.textContent?.trim(),
      kind: item.querySelector(".node-kind")?.textContent?.trim(),
      role: item.dataset.boundaryRole,
      input: item.querySelector(".port-group:first-child")?.textContent?.trim(),
      output: item.querySelector(".port-group:last-child")?.textContent?.trim(),
    })),
  }));

  assert(result.note?.includes("完全な関数実行境界"));
  assert.deepEqual(new Set(result.edgeLabels), new Set(["calls"]));
  assert.equal(
    result.nodes.some(node => node.input?.includes("undeclared") || node.output?.includes("undeclared")),
    false,
  );
  assert(result.nodes.some(node => node.name === "control" && node.role === "entry"));
  assert(result.nodes.some(node => node.name === "sensor" && node.role === "source"));
  assert(result.nodes.some(node => node.name === "lock" && node.role === "sink"));
  assert(result.nodes.some(node => node.name === "step" && node.role === "internal"));

  await page.screenshot({
    path: path.join(outputDirectory, "door-controller-executable-system-boundary.png"),
    fullPage: true,
  });
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified state-first startup and entry/source/sink executable System boundary");
