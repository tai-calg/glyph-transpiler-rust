import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/transition-arrow-clearance");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`, { cache: "no-store" });
      if (response.ok) {
        const state = await response.json();
        if (state.status === "ready") return state;
      }
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Glyph server did not become ready\n${logs.join("")}`);
}

async function stop(child) {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    new Promise(resolve => setTimeout(resolve, 1500)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

const port = 8799;
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
  const url = `http://127.0.0.1:${port}`;
  const state = await waitForServer(url, child, logs);
  const machine = state.views.state.machines.find(item => item.name === "Door") || state.views.state.machines[0];
  assert(machine, "state machine missing");

  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  const errors = [];
  page.on("pageerror", error => errors.push(`pageerror: ${error.message}`));
  page.on("console", message => { if (message.type() === "error") errors.push(`console: ${message.text()}`); });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(expectedCount => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return stage?.dataset.transitionArrowClearanceReady === "true"
      && stage?.dataset.transitionPublicationReady === "true"
      && Number(stage?.dataset.transitionArrowClearancePathCount || 0) === expectedCount;
  }, machine.transitions.length, { timeout: 8000 });
  await page.waitForTimeout(120);

  const audit = await page.evaluate(expectedTransitions => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const selected = (() => {
      const machines = typeof snapshot === "object" && snapshot ? snapshot.views?.state?.machines || [] : [];
      const name = document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;
      return machines.find(item => item.name === name) || machines[0] || null;
    })();
    const nodes = new Map([...(stage?.querySelectorAll(".state-node") || [])].map(node => [node.querySelector(".state-name")?.textContent?.trim() || "", node]));
    const paths = [...(stage?.querySelector(":scope > svg.edge-svg")?.querySelectorAll(":scope > path") || [])].slice(0, expectedTransitions);
    const number = value => Number.parseFloat(value || "0") || 0;
    const unit = (dx, dy) => {
      const length = Math.max(.0001, Math.hypot(dx, dy));
      return { x: dx / length, y: dy / length };
    };
    const boundaryDistance = (node, direction) => {
      const halfWidth = node.offsetWidth / 2;
      const halfHeight = node.offsetHeight / 2;
      const radius = Math.max(0, Math.min(number(getComputedStyle(node).borderTopLeftRadius), halfWidth, halfHeight));
      const ax = Math.abs(direction.x), ay = Math.abs(direction.y), epsilon = .0001;
      const vertical = ax > epsilon ? halfWidth / ax : Number.POSITIVE_INFINITY;
      if (Number.isFinite(vertical) && ay * vertical <= halfHeight - radius + .01) return vertical;
      const horizontal = ay > epsilon ? halfHeight / ay : Number.POSITIVE_INFINITY;
      if (Number.isFinite(horizontal) && ax * horizontal <= halfWidth - radius + .01) return horizontal;
      if (radius <= epsilon) return Math.min(vertical, horizontal);
      const cornerX = (direction.x < 0 ? -1 : 1) * (halfWidth - radius);
      const cornerY = (direction.y < 0 ? -1 : 1) * (halfHeight - radius);
      const projection = direction.x * cornerX + direction.y * cornerY;
      const discriminant = Math.max(0, projection * projection - (cornerX * cornerX + cornerY * cornerY - radius * radius));
      return Math.max(0, projection + Math.sqrt(discriminant));
    };
    const rows = (selected?.transitions || []).map((transition, index) => {
      const target = nodes.get(String(transition.target_state || ""));
      const path = paths[index];
      if (!target || !path) return { missing: true, index };
      const length = path.getTotalLength();
      const end = path.getPointAtLength(length);
      const before = path.getPointAtLength(Math.max(0, length - 8));
      const center = { x: target.offsetLeft + target.offsetWidth / 2, y: target.offsetTop + target.offsetHeight / 2 };
      const outward = unit(end.x - center.x, end.y - center.y);
      const incoming = unit(end.x - before.x, end.y - before.y);
      const towardCenter = unit(center.x - end.x, center.y - end.y);
      const radialDistance = Math.hypot(end.x - center.x, end.y - center.y);
      return {
        missing: false,
        index,
        id: transition.id || `T${index + 1}`,
        selfLoop: transition.source_state === transition.target_state,
        clearance: radialDistance - boundaryDistance(target, outward),
        alignment: incoming.x * towardCenter.x + incoming.y * towardCenter.y,
        declaredClearance: number(path.dataset.arrowNodeClearance),
        d: path.getAttribute("d") || "",
      };
    });
    const marker = stage?.querySelector("#state-arrow");
    return {
      ready: stage?.dataset.transitionArrowClearanceReady || "",
      pathCount: rows.length,
      minClearance: Math.min(...rows.filter(row => !row.missing).map(row => row.clearance)),
      minAlignment: Math.min(...rows.filter(row => !row.missing).map(row => row.alignment)),
      markerRefX: marker?.getAttribute("refX") || "",
      markerUnits: marker?.getAttribute("markerUnits") || "",
      markerWidth: marker?.getAttribute("markerWidth") || "",
      markerHeight: marker?.getAttribute("markerHeight") || "",
      rows,
    };
  }, machine.transitions.length);

  await page.screenshot({ path: path.join(outputDirectory, "door-arrow-clearance.png"), fullPage: true });
  await fs.writeFile(path.join(outputDirectory, "audit.json"), JSON.stringify(audit, null, 2));

  assert.equal(audit.ready, "true", JSON.stringify(audit));
  assert.equal(audit.pathCount, machine.transitions.length, JSON.stringify(audit));
  assert(audit.rows.every(row => !row.missing), JSON.stringify(audit));
  assert(audit.rows.every(row => row.declaredClearance === 6), JSON.stringify(audit));
  assert(audit.minClearance >= 5.5, JSON.stringify(audit));
  assert(audit.minAlignment > 0.1, JSON.stringify(audit));
  assert.equal(audit.markerRefX, "10", JSON.stringify(audit));
  assert.equal(audit.markerUnits, "userSpaceOnUse", JSON.stringify(audit));
  assert.equal(audit.markerWidth, "12", JSON.stringify(audit));
  assert.equal(audit.markerHeight, "12", JSON.stringify(audit));
  assert.deepEqual(errors, [], errors.join("\n"));
  await page.close();
} finally {
  await browser.close();
  await stop(child);
}

console.log("verified state transition arrowheads remain outside rounded state nodes");
