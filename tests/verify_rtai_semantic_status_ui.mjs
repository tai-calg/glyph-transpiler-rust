import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/rtai-semantic-status");
await fs.mkdir(outputDirectory, { recursive: true });

async function start(command, args, port) {
  const logs = [];
  const child = spawn(command, args, {
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
  for (let attempt = 0; attempt < 180; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`app exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`);
      if (response.ok) {
        const state = await response.json();
        if (state.status === "ready") return { child, logs, state, url };
        if (state.status === "error") throw new Error(JSON.stringify(state.diagnostics));
      }
    } catch (error) {
      if (attempt > 170) throw error;
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`app did not become ready\n${logs.join("")}`);
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

async function openStatePage(browser, url, transitionCount) {
  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(expected => {
    const stage = document.querySelector(".graph-stage");
    return stage?.dataset.transitionIoClustersReady === "true"
      && stage?.dataset.rtaiSemanticStatusReady === "true"
      && document.querySelectorAll(".transition-io-cluster[data-rtai-semantic-status]").length === expected;
  }, transitionCount, { timeout: 60_000 });
  return page;
}

function semanticPresentation(element) {
  const pseudo = getComputedStyle(element, "::after");
  return {
    status: element.dataset.rtaiSemanticStatus,
    label: element.dataset.rtaiSemanticLabel,
    reason: element.dataset.rtaiSemanticReason,
    title: element.dataset.rtaiSemanticTitle,
    content: pseudo.content.replace(/^"|"$/g, ""),
    display: pseudo.display,
  };
}

const browser = await chromium.launch({ headless: true });
const processes = [];
try {
  const unknownApp = await start(
    "python3",
    ["glyph.py", "examples/acceptance/motor_safety.glyph"],
    8897,
  );
  processes.push(unknownApp.child);
  const unknownMachine = unknownApp.state.views.state.machines[0];
  const unknownStatuses = unknownMachine.transitions.map(
    transition => transition.rtai_semantic_status?.status,
  );
  assert(unknownStatuses.length > 0);
  assert(unknownStatuses.every(status => status === "unknown"), unknownStatuses.join(","));

  const unknownPage = await openStatePage(
    browser,
    unknownApp.url,
    unknownMachine.transitions.length,
  );
  const unknownClusters = unknownPage.locator(
    '.transition-io-cluster[data-rtai-semantic-status="unknown"]',
  );
  assert.equal(await unknownClusters.count(), unknownMachine.transitions.length);
  const unknownBefore = await unknownClusters.first().evaluate(semanticPresentation);
  assert.equal(unknownBefore.display, "none");
  assert.equal(unknownBefore.content, "Unknown");
  await unknownClusters.first().hover();
  await unknownPage.waitForFunction(() => {
    const cluster = document.querySelector(
      '.transition-io-cluster:hover[data-rtai-semantic-status="unknown"]',
    );
    return cluster && getComputedStyle(cluster, "::after").display !== "none";
  });
  const unknownAfter = await unknownClusters.first().evaluate(semanticPresentation);
  assert.notEqual(unknownAfter.display, "none");
  assert(unknownAfter.title.includes("Unknown"));
  await unknownPage.screenshot({
    path: path.join(outputDirectory, "unknown-hover.png"),
    fullPage: true,
  });
  await unknownPage.close();

  const mayApp = await start(
    "python3",
    ["tests/run_rtai_may_diagram_app.py", "examples/acceptance/rtai_may_projection.glyph"],
    8898,
  );
  processes.push(mayApp.child);
  const mayViews = mayApp.state.views;
  assert.equal(mayViews.rtai_projection_mode, "strict-exact");
  assert.equal(mayViews.strict_projection_campaign?.ready, false);
  assert.equal(
    mayViews.strict_projection_campaign?.machines?.[0]?.effect_contract_coverage_complete,
    true,
  );
  assert.equal(
    mayViews.strict_projection_campaign?.machines?.[0]?.witness_generation_complete,
    false,
  );
  const mayMachine = mayViews.state.machines[0];
  const mayStatuses = mayMachine.transitions.map(
    transition => transition.rtai_semantic_status?.status,
  );
  assert(mayStatuses.length > 0);
  assert(mayStatuses.every(status => status === "may"), mayStatuses.join(","));
  assert(mayMachine.transitions.every(transition => transition.system_action == null));

  const mayPage = await openStatePage(browser, mayApp.url, mayMachine.transitions.length);
  const mayClusters = mayPage.locator(
    '.transition-io-cluster[data-rtai-semantic-status="may"]',
  );
  assert.equal(await mayClusters.count(), mayMachine.transitions.length);
  const mayPresentation = await mayClusters.evaluateAll(elements => elements.map(semanticPresentation));
  assert(mayPresentation.every(item => item.label === "May"));
  assert(mayPresentation.every(item => item.content === "May"));
  assert(mayPresentation.every(item => item.display !== "none"));
  assert(mayPresentation.every(item => item.reason.includes("reachability")));
  await mayPage.screenshot({
    path: path.join(outputDirectory, "may-ui.png"),
    fullPage: true,
  });
  await mayPage.close();

  await fs.writeFile(
    path.join(outputDirectory, "report.json"),
    `${JSON.stringify({
      unknown_transition_count: unknownStatuses.length,
      may_transition_count: mayStatuses.length,
      unknown_hover_visible: true,
      may_visible: true,
    }, null, 2)}\n`,
  );
  console.log(JSON.stringify({
    unknownTransitionCount: unknownStatuses.length,
    mayTransitionCount: mayStatuses.length,
  }));
} finally {
  await browser.close();
  await Promise.all(processes.map(stop));
}
