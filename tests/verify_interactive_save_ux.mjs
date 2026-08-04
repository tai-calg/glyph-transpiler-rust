import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/interactive-save-ux");
await fs.mkdir(outputDirectory, { recursive: true });
const sourcePath = path.join(outputDirectory, "interactive-save-ux.glyph");
const initialSource = await fs.readFile("examples/state_diagrams/traffic_light.glyph", "utf8");
await fs.writeFile(sourcePath, initialSource, "utf8");

const port = 8894;
const url = `http://127.0.0.1:${port}`;
const logs = [];

const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function waitForServer(child) {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`Glyph UX server exited early\n${logs.join("")}`);
    }
    try {
      const response = await fetch(`${url}/api/state`, { cache: "no-store" });
      if (response.ok && (await response.json()).status === "ready") return;
    } catch {}
    await sleep(100);
  }
  throw new Error(`Glyph UX server did not become ready\n${logs.join("")}`);
}

async function stopProcess(child) {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise(resolve => child.once("exit", resolve)),
    sleep(1500),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

async function audit(page) {
  return page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return {
      source: snapshot?.source || "",
      snapshotStatus: snapshot?.status || "",
      persistence: document.querySelector("#glyph-save-state")?.dataset.persistence || "",
      renderState: document.querySelector("#glyph-save-state")?.dataset.render || "",
      saveInFlight: window.GlyphSaveTriggeredRendering?.saveInFlight ?? null,
      editorSource: document.querySelector("#editor")?.value || "",
      saveDisabled: Boolean(document.querySelector("#save")?.disabled),
      saveBusy: document.querySelector("#save")?.getAttribute("aria-busy") || "",
      activeTab: document.querySelector(".tab.active")?.dataset.tab || "",
      staleVisible: document.querySelector("#glyph-stale-banner")?.hidden === false,
      stageMarker: stage?.dataset.uxIdentity || "",
      stageVisibility: stage ? getComputedStyle(stage).visibility : "missing",
      stateNodeCount: document.querySelectorAll(".state-node").length,
      layoutState: stage?.dataset.transitionLayoutState || "",
      publicationReady: stage?.dataset.transitionPublicationReady || "",
    };
  });
}

async function waitForAudit(page, predicate, label, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  let current = null;
  while (Date.now() < deadline) {
    current = await audit(page);
    if (predicate(current)) return current;
    await page.waitForTimeout(50);
  }
  throw new Error(`${label}: ${JSON.stringify(current)}`);
}

async function timedTabSwitch(page, tab) {
  const started = await page.evaluate(() => performance.now());
  await page.click(`button[data-tab="${tab}"]`);
  await page.waitForFunction(
    expected => document.querySelector(".tab.active")?.dataset.tab === expected,
    tab,
    { timeout: 2000 },
  );
  const ended = await page.evaluate(() => performance.now());
  return ended - started;
}

async function measuredFill(page, value) {
  const started = await page.evaluate(() => {
    window.__glyphUxProbe.inputMark = performance.now();
    return window.__glyphUxProbe.inputMark;
  });
  await page.locator("#editor").fill(value);
  const ended = await page.evaluate(() => (
    window.__glyphUxProbe.inputs.at(-1) ?? performance.now()
  ));
  return ended - started;
}

async function sampleAnimationFrames(page, count = 16) {
  return page.evaluate(async frameCount => {
    const gaps = [];
    let previous = performance.now();
    for (let index = 0; index < frameCount; index += 1) {
      const current = await new Promise(resolve => requestAnimationFrame(resolve));
      gaps.push(current - previous);
      previous = current;
    }
    window.__glyphUxProbe.rafGaps.push(...gaps);
    return gaps;
  }, count);
}

function percentile(values, ratio) {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * ratio))];
}

const child = spawn(
  "python3",
  ["tests/run_interactive_save_ux_server.py", sourcePath],
  {
    env: {
      ...process.env,
      GLYPH_DIAGRAM_PORT: String(port),
      GLYPH_DIAGRAM_NO_BROWSER: "1",
      GLYPH_UX_COMPILE_DELAY: "2.5",
      PYTHONUNBUFFERED: "1",
    },
    stdio: ["ignore", "pipe", "pipe"],
  },
);
child.stdout.on("data", chunk => logs.push(chunk.toString()));
child.stderr.on("data", chunk => logs.push(chunk.toString()));

const browser = await chromium.launch({ headless: true });
try {
  await waitForServer(child);
  const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });
  const browserErrors = [];
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.stack || error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });

  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => (
    document.querySelector("#status")?.textContent === "ready"
    && window.GlyphSaveTriggeredRendering?.version === 4
  ), null, { timeout: 10_000 });
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return document.querySelectorAll(".state-node").length > 0
      && stage?.dataset.transitionLayoutState === "ready"
      && stage.dataset.transitionPublicationReady === "true";
  }, null, { timeout: 8000 });

  await page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    stage.dataset.uxIdentity = "initial-committed-diagram";
    window.__glyphUxProbe = {
      actionStart: 0,
      inputMark: 0,
      events: [],
      inputs: [],
      longTasks: [],
      rafGaps: [],
    };
    document.addEventListener("glyph-save-state-changed", event => {
      window.__glyphUxProbe.events.push({
        time: performance.now(),
        persistence: event.detail?.persistence || "",
        render: event.detail?.render || "",
        stale: Boolean(event.detail?.stale),
      });
    });
    document.querySelector("#editor")?.addEventListener("input", () => {
      window.__glyphUxProbe.inputs.push(performance.now());
    });
    try {
      const observer = new PerformanceObserver(entries => {
        for (const entry of entries.getEntries()) {
          window.__glyphUxProbe.longTasks.push(entry.duration);
        }
      });
      observer.observe({ entryTypes: ["longtask"] });
      window.__glyphUxProbe.longTaskObserver = observer;
    } catch {}
  });

  await page.route("**/api/save", async route => {
    await sleep(900);
    await route.continue();
  });

  const submittedSource = `${initialSource}\n# submitted for interactive UX validation\n`;
  const queuedSource = `${submittedSource}# queued while save acknowledgement is pending\n`;
  await page.locator("#editor").fill(submittedSource);
  const saveActionStart = await page.evaluate(() => {
    window.__glyphUxProbe.actionStart = performance.now();
    return window.__glyphUxProbe.actionStart;
  });
  await page.click("#save");
  const saving = await waitForAudit(
    page,
    value => value.saveInFlight === true && value.renderState === "saving",
    "save feedback was not presented",
  );
  const saveFeedbackLatency = await page.evaluate(start => {
    const event = window.__glyphUxProbe.events.find(item => (
      item.time >= start && item.render === "saving"
    ));
    return event ? event.time - start : Number.POSITIVE_INFINITY;
  }, saveActionStart);
  assert.equal(saving.saveDisabled, false, "Save became unavailable during acknowledgement");
  assert.equal(saving.saveBusy, "true", "Save did not expose its pending state");

  const inputLatencyDuringSave = await measuredFill(page, queuedSource);
  const ioSwitchDuringSave = await timedTabSwitch(page, "io");
  const stateSwitchDuringSave = await timedTabSwitch(page, "state");
  await page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    stage.dataset.uxIdentity = "precompile-committed-diagram";
  });
  const stillSaving = await audit(page);
  assert.equal(stillSaving.saveInFlight, true, "save acknowledgement completed before interaction probe");
  await page.click("#save");

  const compiling = await waitForAudit(
    page,
    value => value.snapshotStatus === "compiling"
      && value.renderState === "compiling"
      && value.saveInFlight === false
      && value.editorSource === queuedSource,
    "queued save did not enter background compilation",
  );
  await page.unroute("**/api/save");
  assert.equal(compiling.staleVisible, true, "compilation did not identify the visible diagram as stale");
  assert.equal(compiling.stageMarker, "precompile-committed-diagram", "compilation replaced the committed diagram");
  assert.equal(compiling.stageVisibility, "visible");
  assert(compiling.stateNodeCount > 0, "state diagram disappeared during compilation");

  const rafDuringCompile = await sampleAnimationFrames(page);
  const ioSwitchDuringCompile = await timedTabSwitch(page, "io");
  const stateSwitchDuringCompile = await timedTabSwitch(page, "state");
  const settingsStarted = await page.evaluate(() => performance.now());
  await page.click("#glyph-settings");
  await page.locator("#glyph-settings-close").waitFor({ state: "visible", timeout: 2000 });
  const settingsOpened = await page.evaluate(() => performance.now());
  await page.click("#glyph-settings-close");

  const localSource = `${queuedSource}# typed while background compilation continues\n`;
  const inputLatencyDuringCompile = await measuredFill(page, localSource);
  const dirtyDuringCompile = await waitForAudit(
    page,
    value => value.persistence === "unsaved"
      && value.snapshotStatus === "compiling"
      && value.editorSource === localSource,
    "editing was not preserved during background compilation",
  );
  assert.equal(dirtyDuringCompile.stageMarker, "precompile-committed-diagram");
  await page.screenshot({
    path: path.join(outputDirectory, "interactive-during-compilation.png"),
    fullPage: false,
  });

  await waitForAudit(
    page,
    value => value.source === queuedSource
      && value.snapshotStatus === "ready"
      && value.persistence === "unsaved"
      && value.editorSource === localSource,
    "compiled source did not settle without overwriting the newer editor buffer",
  );

  const finalSaveStartedWall = Date.now();
  const finalSaveStarted = await page.evaluate(() => {
    window.__glyphUxProbe.finalSaveStart = performance.now();
    return window.__glyphUxProbe.finalSaveStart;
  });
  await page.click("#save");
  await waitForAudit(
    page,
    value => value.snapshotStatus === "compiling"
      && value.renderState === "compiling"
      && value.editorSource === localSource,
    "final save did not acknowledge and enter compilation",
  );
  const finalCompileFeedback = await page.evaluate(start => {
    const event = window.__glyphUxProbe.events.find(item => (
      item.time >= start && item.render === "compiling"
    ));
    return event ? event.time - start : Number.POSITIVE_INFINITY;
  }, finalSaveStarted);
  const rafDuringFinalCompile = await sampleAnimationFrames(page);
  const finalState = await waitForAudit(
    page,
    value => value.source === localSource
      && value.snapshotStatus === "ready"
      && value.persistence === "saved"
      && value.renderState === "ready"
      && value.editorSource === localSource,
    "final save did not settle",
  );
  const finalSaveDuration = Date.now() - finalSaveStartedWall;
  assert.equal(finalState.staleVisible, false);
  assert(finalState.stateNodeCount > 0);
  assert.equal(await fs.readFile(sourcePath, "utf8"), localSource);

  const probe = await page.evaluate(() => ({
    events: window.__glyphUxProbe.events,
    longTasks: window.__glyphUxProbe.longTasks,
    rafGaps: window.__glyphUxProbe.rafGaps,
  }));
  const renderSequence = probe.events
    .map(event => event.render)
    .filter((value, index, values) => index === 0 || value !== values[index - 1]);
  assert(renderSequence.includes("saving"), `missing saving state: ${renderSequence.join(" -> ")}`);
  assert(renderSequence.includes("compiling"), `missing compiling state: ${renderSequence.join(" -> ")}`);
  assert.equal(renderSequence.at(-1), "ready", `final state is not ready: ${renderSequence.join(" -> ")}`);
  assert.equal(renderSequence.includes("error"), false, `unexpected error state: ${renderSequence.join(" -> ")}`);

  const allRafGaps = [...rafDuringCompile, ...rafDuringFinalCompile];
  const maxLongTask = Math.max(0, ...probe.longTasks);
  const maxRafGap = Math.max(0, ...allRafGaps);
  const p95RafGap = percentile(allRafGaps, 0.95);
  const settingsOpenLatency = settingsOpened - settingsStarted;

  assert(saveFeedbackLatency <= 250, `save feedback took ${saveFeedbackLatency.toFixed(1)}ms`);
  assert(inputLatencyDuringSave <= 300, `input during save took ${inputLatencyDuringSave.toFixed(1)}ms`);
  assert(inputLatencyDuringCompile <= 300, `input during compile took ${inputLatencyDuringCompile.toFixed(1)}ms`);
  assert(ioSwitchDuringSave <= 350, `I/O tab during save took ${ioSwitchDuringSave.toFixed(1)}ms`);
  assert(stateSwitchDuringSave <= 350, `State tab during save took ${stateSwitchDuringSave.toFixed(1)}ms`);
  assert(ioSwitchDuringCompile <= 350, `I/O tab during compile took ${ioSwitchDuringCompile.toFixed(1)}ms`);
  assert(stateSwitchDuringCompile <= 350, `State tab during compile took ${stateSwitchDuringCompile.toFixed(1)}ms`);
  assert(settingsOpenLatency <= 350, `Settings during compile took ${settingsOpenLatency.toFixed(1)}ms`);
  assert(finalCompileFeedback <= 750, `compile acknowledgement took ${finalCompileFeedback.toFixed(1)}ms`);
  assert(finalSaveDuration <= 4500, `final save and compile took ${finalSaveDuration}ms`);
  assert(p95RafGap <= 120, `animation-frame p95 was ${p95RafGap.toFixed(1)}ms`);
  assert(maxRafGap <= 400, `maximum animation-frame gap was ${maxRafGap.toFixed(1)}ms`);
  assert(maxLongTask <= 250, `main-thread long task was ${maxLongTask.toFixed(1)}ms`);
  assert.deepEqual(browserErrors, [], `interactive UX emitted browser errors:\n${browserErrors.join("\n")}`);

  const report = {
    thresholdsMs: {
      saveFeedback: 250,
      input: 300,
      tabOrSettings: 350,
      compileAcknowledgement: 750,
      finalSave: 4500,
      animationFrameP95: 120,
      animationFrameMaximum: 400,
      longTaskMaximum: 250,
    },
    measurementsMs: {
      saveFeedbackLatency,
      inputLatencyDuringSave,
      inputLatencyDuringCompile,
      ioSwitchDuringSave,
      stateSwitchDuringSave,
      ioSwitchDuringCompile,
      stateSwitchDuringCompile,
      settingsOpenLatency,
      finalCompileFeedback,
      finalSaveDuration,
      animationFrameP95: p95RafGap,
      animationFrameMaximum: maxRafGap,
      longTaskMaximum: maxLongTask,
    },
    renderSequence,
    eventCount: probe.events.length,
    stateNodeCount: finalState.stateNodeCount,
  };
  await fs.writeFile(
    path.join(outputDirectory, "ux-report.json"),
    `${JSON.stringify(report, null, 2)}\n`,
    "utf8",
  );
  await page.screenshot({
    path: path.join(outputDirectory, "interactive-final.png"),
    fullPage: false,
  });
  await page.close();
  console.log(JSON.stringify(report));
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified responsive editing, navigation, queued saves, stale-view continuity, and bounded browser stalls during delayed save and compilation");
