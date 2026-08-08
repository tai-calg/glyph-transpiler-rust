import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/large-graph-interaction-ux");
await fs.mkdir(outputDirectory, { recursive: true });
const sourcePath = path.join(outputDirectory, "large-graph.glyph");
const stateCount = 64;
const states = Array.from({ length: stateCount }, (_, index) => `S${index}`);
const source = [
  "machine LargeGraph(state:LargeState,input:LargeInput)",
  "  select=state.mode",
  "  init=LargeState(S0)",
  "  next=large_step(state,input)",
  "  success=S1",
  `  failure=S${stateCount - 1}`,
  "",
  "*LargeInput(forward:B,back:B,jump:B)",
  `+LargeMode=${states.join("|")}`,
  "*LargeState(mode:LargeMode)",
  "",
  ">large_step(state:LargeState,input:LargeInput):LargeState",
  ...states.flatMap((state, index) => [
    `  state.mode==${state}&input.forward >> LargeState(S${(index + 1) % stateCount})`,
    `  state.mode==${state}&input.back >> LargeState(S${(index - 1 + stateCount) % stateCount})`,
    `  state.mode==${state}&input.jump >> LargeState(S${(index + 7) % stateCount})`,
  ]),
  "  _ >> state",
  "",
].join("\n");
await fs.writeFile(sourcePath, source, "utf8");

const port = 8897;
const url = `http://127.0.0.1:${port}`;
const logs = [];
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function waitForServer(child) {
  for (let attempt = 0; attempt < 300; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph process exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`, { cache: "no-store" });
      if (response.ok && (await response.json()).status === "ready") return;
    } catch {}
    await sleep(100);
  }
  throw new Error(`Glyph server did not become ready\n${logs.join("")}`);
}

async function stop(child) {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    sleep(1500),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

async function workspaceAudit(page) {
  return page.evaluate(() => ({
    workspace: window.glyphStateDiagramWorkspace?.audit?.() ?? null,
    transaction: window.glyphTransitionLayoutTransaction?.audit?.() ?? null,
    layoutState: document.querySelector(".state-node")?.closest(".graph-stage")?.dataset.transitionLayoutState || "",
    publicationReady: document.querySelector(".state-node")?.closest(".graph-stage")?.dataset.transitionPublicationReady || "",
  }));
}

function percentile(values, ratio) {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * ratio))];
}

const child = spawn("python3", ["glyph.py", sourcePath], {
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
  await waitForServer(child);
  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  const browserErrors = [];
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.stack || error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });

  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(expectedStateCount => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return window.glyphStateDiagramWorkspace?.version === 4
      && window.glyphTransitionLayoutTransaction?.version === 9
      && document.querySelectorAll(".state-node").length === expectedStateCount
      && document.querySelectorAll("path.state-transition-path").length >= expectedStateCount * 3
      && stage?.dataset.stateDiagramWorkspaceGeometryReady === "true"
      && stage.dataset.transitionIoClustersReady === "true"
      && stage.dataset.transitionLayoutState === "ready";
  }, stateCount, { timeout: 15_000 });

  await page.waitForTimeout(350);
  const baseline = await workspaceAudit(page);
  assert.equal(baseline.workspace?.ok, true, JSON.stringify(baseline));
  assert.equal(baseline.workspace?.dragBudgetMs, 8, JSON.stringify(baseline));
  assert.equal(baseline.transaction?.frameSliceBudgetMs, 8, JSON.stringify(baseline));
  assert(baseline.transaction?.ownerDispatchMaxMs <= 8, JSON.stringify(baseline));

  await page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const svg = stage?.querySelector(":scope > svg.edge-svg");
    const changedPaths = new Set();
    const pathObserver = new MutationObserver(records => {
      for (const record of records) {
        if (record.type !== "attributes" || record.attributeName !== "d") continue;
        const path = record.target;
        changedPaths.add(path.dataset.transitionId || `path-${[...svg.children].indexOf(path)}`);
      }
    });
    if (svg) pathObserver.observe(svg, { subtree: true, attributes: true, attributeFilter: ["d"] });

    const probe = {
      changedPaths,
      pathObserver,
      longTasks: [],
      rafGaps: [],
      rafActive: true,
      previousFrame: performance.now(),
    };
    try {
      const longTaskObserver = new PerformanceObserver(entries => {
        for (const entry of entries.getEntries()) probe.longTasks.push(entry.duration);
      });
      longTaskObserver.observe({ entryTypes: ["longtask"] });
      probe.longTaskObserver = longTaskObserver;
    } catch {}
    const tick = now => {
      if (!probe.rafActive) return;
      probe.rafGaps.push(now - probe.previousFrame);
      probe.previousFrame = now;
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    window.__glyphLargeGraphProbe = probe;
  });

  const node = page.locator(".state-node", { hasText: "S32" }).first();
  await node.scrollIntoViewIfNeeded();
  const box = await node.boundingBox();
  assert(box, "drag target is not visible");
  const startX = box.x + box.width / 2;
  const startY = box.y + box.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  for (let step = 1; step <= 24; step += 1) {
    await page.mouse.move(startX + step * 3, startY + Math.sin(step / 3) * 18);
    await page.waitForTimeout(18);
  }

  const duringDrag = await page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const probe = window.__glyphLargeGraphProbe;
    return {
      workspace: window.glyphStateDiagramWorkspace?.audit?.() ?? null,
      changedPathCount: probe?.changedPaths?.size ?? 0,
      dragBudgetExceeded: stage?.dataset.stateDiagramWorkspaceDragBudgetExceeded || "",
      incidentEdgeCount: Number(stage?.dataset.stateDiagramWorkspaceIncidentEdgeCount || 0),
      dragMaxDurationMs: Number(stage?.dataset.stateDiagramWorkspaceDragMaxDurationMs || 0),
      rafGaps: [...(probe?.rafGaps || [])],
      longTasks: [...(probe?.longTasks || [])],
    };
  });

  assert.equal(
    duringDrag.workspace?.fullGeometryPasses,
    baseline.workspace?.fullGeometryPasses,
    `full graph geometry ran while pointer was held: ${JSON.stringify(duringDrag)}`,
  );
  assert(
    duringDrag.workspace?.incidentGeometryPasses > baseline.workspace?.incidentGeometryPasses,
    `incident geometry did not run: ${JSON.stringify(duringDrag)}`,
  );
  assert(
    duringDrag.incidentEdgeCount <= 8,
    `drag touched too many incident edges: ${JSON.stringify(duringDrag)}`,
  );
  assert(
    duringDrag.changedPathCount <= 8,
    `drag mutated non-incident transition paths: ${JSON.stringify(duringDrag)}`,
  );
  assert.equal(duringDrag.dragBudgetExceeded, "false", JSON.stringify(duringDrag));
  assert(duringDrag.dragMaxDurationMs <= 8, JSON.stringify(duringDrag));

  await page.mouse.up();
  await page.waitForFunction(previousPasses => {
    const audit = window.glyphStateDiagramWorkspace?.audit?.();
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return audit?.fullGeometryPasses > previousPasses
      && stage?.dataset.transitionLayoutState === "ready"
      && stage.dataset.transitionPublicationReady === "true"
      && stage.dataset.initialRouteReady === "true";
  }, baseline.workspace.fullGeometryPasses, { timeout: 8000 });

  const finalProbe = await page.evaluate(() => {
    const probe = window.__glyphLargeGraphProbe;
    probe.rafActive = false;
    probe.pathObserver?.disconnect();
    probe.longTaskObserver?.disconnect();
    return {
      rafGaps: [...probe.rafGaps],
      longTasks: [...probe.longTasks],
      workspace: window.glyphStateDiagramWorkspace?.audit?.() ?? null,
      transaction: window.glyphTransitionLayoutTransaction?.audit?.() ?? null,
    };
  });

  const p95RafGap = percentile(finalProbe.rafGaps, 0.95);
  const maxRafGap = Math.max(0, ...finalProbe.rafGaps);
  const maxLongTask = Math.max(0, ...finalProbe.longTasks);
  assert(p95RafGap <= 80, `large-graph drag animation-frame p95 was ${p95RafGap.toFixed(1)}ms`);
  assert(maxRafGap <= 180, `large-graph drag maximum animation-frame gap was ${maxRafGap.toFixed(1)}ms`);
  assert(maxLongTask <= 120, `large-graph drag main-thread long task was ${maxLongTask.toFixed(1)}ms`);
  assert(finalProbe.transaction?.ownerDispatchMaxMs <= 8, JSON.stringify(finalProbe.transaction));
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));

  const report = {
    stateCount,
    transitionCount: stateCount * 3 + 1,
    dragIncidentEdgeCount: duringDrag.incidentEdgeCount,
    changedPathCountDuringDrag: duringDrag.changedPathCount,
    fullGeometryPassesBeforeDrag: baseline.workspace.fullGeometryPasses,
    fullGeometryPassesAfterDrag: finalProbe.workspace.fullGeometryPasses,
    incidentGeometryPassesBeforeDrag: baseline.workspace.incidentGeometryPasses,
    incidentGeometryPassesDuringDrag: duringDrag.workspace.incidentGeometryPasses,
    dragMaxDurationMs: duringDrag.dragMaxDurationMs,
    animationFrameP95Ms: p95RafGap,
    animationFrameMaximumMs: maxRafGap,
    longTaskMaximumMs: maxLongTask,
    transactionOwnerDispatchMaxMs: finalProbe.transaction.ownerDispatchMaxMs,
  };
  await fs.writeFile(path.join(outputDirectory, "ux-report.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await page.screenshot({ path: path.join(outputDirectory, "large-graph-after-drag.png"), fullPage: false });
  console.log(JSON.stringify(report));
  await page.close();
} finally {
  await browser.close();
  await stop(child);
}

console.log("verified incident-only node dragging and frame-bounded transaction dispatch on a large state graph");
