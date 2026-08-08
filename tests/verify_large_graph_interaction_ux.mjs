import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/large-graph-interaction-ux");
await fs.mkdir(outputDirectory, { recursive: true });
const stateCount = 64;
const transitionCount = stateCount * 3;
const port = 8897;
const url = `http://127.0.0.1:${port}`;
const logs = [];
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function waitForServer(child) {
  for (let attempt = 0; attempt < 180; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph process exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`, { cache: "no-store" });
      if (response.ok) {
        const state = await response.json();
        if (state.status === "ready"
          && state.views?.large_graph_fixture?.state_count === stateCount
          && state.views?.large_graph_fixture?.transition_count === transitionCount) return;
        if (state.status === "error") throw new Error(`large graph fixture failed: ${JSON.stringify(state.diagnostics || [])}`);
      }
    } catch (error) {
      if (String(error?.message || error).startsWith("large graph fixture failed:")) throw error;
    }
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
    transactionGeneration: window.glyphTransitionLayoutTransaction?.generation ?? null,
    transactionCompletedGeneration: window.glyphTransitionLayoutTransaction?.completedGeneration ?? null,
    layoutState: document.querySelector(".state-node")?.closest(".graph-stage")?.dataset.transitionLayoutState || "",
    publicationReady: document.querySelector(".state-node")?.closest(".graph-stage")?.dataset.transitionPublicationReady || "",
  }));
}

async function waitForWorkspaceQuiescence(page, label) {
  let stable = 0;
  let previous = "";
  let current = null;
  for (let attempt = 0; attempt < 50; attempt += 1) {
    current = await workspaceAudit(page);
    const signature = JSON.stringify({
      fullGeometryPasses: current.workspace?.fullGeometryPasses ?? -1,
      layoutState: current.layoutState,
      publicationReady: current.publicationReady,
      transactionGeneration: current.transactionGeneration,
      transactionCompletedGeneration: current.transactionCompletedGeneration,
    });
    const ready = current.workspace?.ok === true
      && current.workspace?.dragActive === false
      && current.layoutState === "ready"
      && current.publicationReady === "true"
      && current.transactionGeneration === current.transactionCompletedGeneration;
    if (ready && signature === previous) {
      stable += 1;
      if (stable >= 5) return current;
    } else {
      stable = 0;
    }
    previous = signature;
    await page.waitForTimeout(100);
  }
  throw new Error(`${label} did not become quiescent: ${JSON.stringify(current)}`);
}

async function findNodeHitPoint(page, stateName) {
  return page.evaluate(name => {
    const node = [...document.querySelectorAll(".state-node")].find(candidate => (
      candidate.querySelector(".state-name,.node-name")?.textContent?.trim() === name
    ));
    if (!node) return { ok: false, reason: "node-missing" };
    const rect = node.getBoundingClientRect();
    const fractions = [
      [0.5, 0.5],
      [0.3, 0.3],
      [0.7, 0.3],
      [0.3, 0.7],
      [0.7, 0.7],
      [0.5, 0.25],
      [0.5, 0.75],
      [0.25, 0.5],
      [0.75, 0.5],
    ];
    const blockers = [];
    for (const [fx, fy] of fractions) {
      const x = rect.left + rect.width * fx;
      const y = rect.top + rect.height * fy;
      const hit = document.elementFromPoint(x, y);
      const hitNode = hit?.closest?.(".state-node") || null;
      if (hitNode === node) {
        return {
          ok: true,
          x,
          y,
          target: hit?.tagName || "",
          targetClass: hit?.className?.baseVal || hit?.className || "",
        };
      }
      blockers.push({
        fx,
        fy,
        tag: hit?.tagName || "",
        className: hit?.className?.baseVal || hit?.className || "",
        state: hitNode?.querySelector?.(".state-name,.node-name")?.textContent?.trim() || "",
      });
    }
    return {
      ok: false,
      reason: "node-has-no-hit-testable-point",
      rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
      blockers,
    };
  }, stateName);
}

function percentile(values, ratio) {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * ratio))];
}

const child = spawn("python3", ["tests/run_large_graph_interaction_ux_server.py"], {
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
  await page.waitForFunction(expected => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return window.glyphStateDiagramWorkspace?.version === 4
      && window.glyphTransitionLayoutTransaction?.version === 9
      && document.querySelectorAll(".state-node").length === expected.states
      && document.querySelectorAll("path.state-transition-path").length >= expected.transitions
      && stage?.dataset.stateDiagramWorkspaceGeometryReady === "true"
      && stage.dataset.transitionIoClustersReady === "true"
      && stage.dataset.transitionLayoutState === "ready";
  }, { states: stateCount, transitions: transitionCount }, { timeout: 15_000 });

  const initialQuiescent = await waitForWorkspaceQuiescence(page, "initial large graph");
  assert.equal(initialQuiescent.workspace?.dragBudgetMs, 8, JSON.stringify(initialQuiescent));
  assert.equal(initialQuiescent.transaction?.frameSliceBudgetMs, 8, JSON.stringify(initialQuiescent));
  assert(initialQuiescent.transaction?.ownerDispatchMaxMs <= 8, JSON.stringify(initialQuiescent));

  const targetName = "S32";
  const node = page.locator(".state-node", { hasText: targetName }).first();
  await node.scrollIntoViewIfNeeded();
  await waitForWorkspaceQuiescence(page, "large graph after target reveal");
  const hitPoint = await findNodeHitPoint(page, targetName);
  assert.equal(hitPoint.ok, true, `large-graph drag target is not hit-testable: ${JSON.stringify(hitPoint)}`);
  const startX = hitPoint.x;
  const startY = hitPoint.y;

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

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.waitForFunction(() => window.glyphStateDiagramWorkspace?.audit?.().dragActive === true, null, { timeout: 1500 });
  const pressedBaseline = await workspaceAudit(page);
  assert.equal(pressedBaseline.workspace?.dragActive, true, JSON.stringify(pressedBaseline));
  await page.evaluate(() => window.__glyphLargeGraphProbe?.changedPaths?.clear?.());

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
    pressedBaseline.workspace?.fullGeometryPasses,
    `full graph geometry ran while pointer was held: ${JSON.stringify(duringDrag)}`,
  );
  assert(
    duringDrag.workspace?.incidentGeometryPasses > pressedBaseline.workspace?.incidentGeometryPasses,
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
      && audit.dragActive === false
      && stage?.dataset.transitionLayoutState === "ready"
      && stage.dataset.transitionPublicationReady === "true"
      && stage.dataset.initialRouteReady === "true";
  }, pressedBaseline.workspace.fullGeometryPasses, { timeout: 8000 });

  const finalProbe = await page.evaluate(() => {
    const probe = window.__glyphLargeGraphProbe;
    probe.rafActive = false;
    probe.pathObserver?.disconnect();
    probe.longTaskObserver?.disconnect();
    return {
      workspace: window.glyphStateDiagramWorkspace?.audit?.() ?? null,
      transaction: window.glyphTransitionLayoutTransaction?.audit?.() ?? null,
    };
  });

  const p95RafGap = percentile(duringDrag.rafGaps, 0.95);
  const maxRafGap = Math.max(0, ...duringDrag.rafGaps);
  const maxLongTask = Math.max(0, ...duringDrag.longTasks);
  assert(p95RafGap <= 80, `large-graph drag animation-frame p95 was ${p95RafGap.toFixed(1)}ms`);
  assert(maxRafGap <= 180, `large-graph drag maximum animation-frame gap was ${maxRafGap.toFixed(1)}ms`);
  assert(maxLongTask <= 120, `large-graph drag main-thread long task was ${maxLongTask.toFixed(1)}ms`);
  assert(finalProbe.transaction?.ownerDispatchMaxMs <= 8, JSON.stringify(finalProbe.transaction));
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));

  const report = {
    stateCount,
    transitionCount,
    targetName,
    hitTarget: hitPoint.target,
    hitTargetClass: hitPoint.targetClass,
    dragIncidentEdgeCount: duringDrag.incidentEdgeCount,
    changedPathCountDuringDrag: duringDrag.changedPathCount,
    fullGeometryPassesAtPress: pressedBaseline.workspace.fullGeometryPasses,
    fullGeometryPassesDuringDrag: duringDrag.workspace.fullGeometryPasses,
    fullGeometryPassesAfterDrag: finalProbe.workspace.fullGeometryPasses,
    incidentGeometryPassesAtPress: pressedBaseline.workspace.incidentGeometryPasses,
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

console.log("verified incident-only node dragging and frame-bounded transaction dispatch on a 64-state / 192-transition view");