import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/localized-semantic-canvas");
await fs.mkdir(outputDirectory, { recursive: true });
const sourcePath = path.join(outputDirectory, "provisional-trigger.glyph");
const originalSource = `+Mode=Idle|Active|Faulted
+Event=Start|Stop
*Input(event:Event,legacy_alarm:B,allowed:B)
*State(mode:Mode)

machine Demo(state:State,input:Input)
  select=state.mode
  init=State(Idle)
  next=step(state,input)
  success=Active
  failure=Faulted

>step(state:State,input:Input):State
  state.mode==Idle&input.event==Start&input.allowed >> State(Active)
  state.mode==Active&input.legacy_alarm >> State(Faulted)
  _ >> state
`;
await fs.writeFile(sourcePath, originalSource, "utf8");

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 160; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph process exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`);
      if (response.ok) {
        const state = await response.json();
        if (state.status === "ready") return state;
      }
    } catch {}
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

async function waitForSavedSource(page, source, status = "ready") {
  const deadline = Date.now() + 60_000;
  let audit = null;
  while (Date.now() < deadline) {
    audit = await page.evaluate(() => ({
      source: snapshot?.source ?? null,
      snapshotStatus: snapshot?.status ?? null,
      version: Number(snapshot?.version || 0),
      digest: snapshot?.digest || "",
      renderedDigest: snapshot?.rendered_digest || "",
      editorSource: document.querySelector("#editor")?.value || "",
      statusText: document.querySelector("#status")?.textContent || "",
      persistence: document.querySelector("#glyph-save-state")?.dataset.persistence || "",
      renderState: document.querySelector("#glyph-save-state")?.dataset.render || "",
      saveInFlight: window.GlyphSaveTriggeredRendering?.saveInFlight ?? null,
      baseDigest: window.GlyphSaveTriggeredRendering?.baseDigest || "",
      conflict: window.GlyphSaveTriggeredRendering?.conflict || null,
      saveDisabled: Boolean(document.querySelector("#save")?.disabled),
      diagnostics: document.querySelector("#diagnostics")?.textContent || "",
    }));
    if (
      audit.source === source
      && audit.snapshotStatus === status
      && audit.saveInFlight === false
    ) return audit;
    await page.waitForTimeout(100);
  }
  throw new Error(`save did not settle: ${JSON.stringify(audit)}`);
}

async function saveSource(page, source, status = "ready") {
  await page.locator("#editor").fill(source);
  await page.click("#save");
  await waitForSavedSource(page, source, status);
}

const logs = [];
const port = 8897;
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
  const url = `http://127.0.0.1:${port}`;
  const apiState = await waitForServer(url, child, logs);
  const machine = apiState.views.state.machines.find(item => item.name === "Demo");
  assert(machine, "Demo machine missing from compiler-derived state view");
  const expectedFailureTransitions = machine.transitions.filter(item => item.outcome === "failure").length;
  assert(expectedFailureTransitions > 0, "fixture must contain failure-state transitions");

  const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });
  const browserErrors = [];
  page.on("pageerror", error => browserErrors.push(error.stack || error.message));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.classList.contains("ready"));
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return document.querySelector(".tab.active")?.dataset.tab === "state"
      && stage?.dataset.transitionLayoutState === "ready"
      && stage?.dataset.transitionPublicationReady === "true"
      && stage?.dataset.transitionIoClustersReady === "true"
      && stage?.dataset.transitionLayoutProfile === "ordinary"
      && stage?.dataset.stateDiagramWorkspaceGeometryReady === "true"
      && stage?.dataset.initialRouteReady === "true"
      && document.querySelectorAll(".transition-index .transition-detail").length > 0
      && document.querySelector("#glyph-settings")
      && document.querySelector("#glyph-save-state")
      && window.GlyphSaveTriggeredRendering?.version === 4
      && !stage?.dataset.transitionLayoutError;
  }, null, { timeout: 10_000 });

  assert.equal(await page.locator("#compile").count(), 0);
  assert.equal((await page.locator("#save").textContent()).trim(), "保存して描画");
  assert.equal(await page.locator("#save").getAttribute("aria-label"), "保存して描画 (Ctrl/Cmd+S)");
  assert.equal(await page.locator("html").getAttribute("lang"), "ja");
  assert.equal(await page.locator("#glyph-save-state").getAttribute("data-persistence"), "saved");
  assert.equal(await page.locator("#glyph-save-state").getAttribute("data-render"), "ready");
  const japaneseWarnings = await page.locator(".analysis-panel").textContent();
  assert(japaneseWarnings.includes("暫定的に入力"), japaneseWarnings);

  const semanticLabels = await page.locator(".transition-io-cluster").evaluateAll(elements => (
    elements.map(element => ({
      id: element.dataset.transitionId || "",
      input: element.dataset.inputValue || "",
      guard: element.dataset.guardValue || "",
      action: element.dataset.actionValue || "",
      value: element.dataset.ioValue || "",
    }))
  ));
  assert(
    semanticLabels.some(item => (
      item.input === "Start"
      && item.guard === "input.allowed"
      && item.value === "Start [input.allowed]"
    )),
    JSON.stringify(semanticLabels),
  );
  assert(
    semanticLabels.some(item => (
      item.input === "? input.legacy_alarm"
      && item.guard === ""
      && item.value === "? input.legacy_alarm"
    )),
    JSON.stringify(semanticLabels),
  );
  assert(
    semanticLabels.every(item => item.guard !== "input.legacy_alarm"),
    JSON.stringify(semanticLabels),
  );
  assert(
    semanticLabels.every(item => item.action === ""),
    JSON.stringify(semanticLabels),
  );

  const placement = await page.evaluate(() => {
    const clusters = [...document.querySelectorAll(".transition-io-cluster")];
    const nodes = [...document.querySelectorAll(".state-node")];
    const overlaps = (a, b, gap = 2) => !(
      a.right + gap <= b.left || b.right + gap <= a.left
      || a.bottom + gap <= b.top || b.bottom + gap <= a.top
    );
    const clusterRects = clusters.map(cluster => cluster.getBoundingClientRect());
    const nodeRects = nodes.map(node => node.getBoundingClientRect());
    const visibleLegacyLabels = [...document.querySelectorAll(".transition-label")].filter(label => {
      const style = getComputedStyle(label);
      return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0;
    });
    return {
      distances: clusters.map(cluster => Number(cluster.dataset.ioDistance || 0)),
      clusterOverlap: clusterRects.some((rect, index) => clusterRects.slice(index + 1).some(other => overlaps(rect, other))),
      nodeOverlap: clusterRects.some(rect => nodeRects.some(node => overlaps(rect, node))),
      ioCount: clusters.filter(cluster => cluster.querySelector('.transition-io-node[data-io-kind="io"]')).length,
      inputCount: document.querySelectorAll('.transition-io-node[data-io-kind="input"]').length,
      outputCount: document.querySelectorAll('.transition-io-node[data-io-kind="output"]').length,
      guardNodeCount: document.querySelectorAll('.transition-io-node[data-io-kind="guard"]').length,
      failureClusterCount: document.querySelectorAll(".transition-io-cluster.failure-transition").length,
      failureErrorCount: document.querySelectorAll(".transition-io-cluster .transition-io-error").length,
      combinedValues: clusters.map(cluster => cluster.querySelector('.transition-io-node[data-io-kind="io"] .transition-io-value')?.textContent || ""),
      semanticActions: clusters.map(cluster => cluster.dataset.actionValue || ""),
      visibleLegacyLabels: visibleLegacyLabels.length,
    };
  });
  assert(placement.distances.length > 0);
  assert(placement.distances.every(value => value <= 96.5), placement.distances.join(", "));
  assert.equal(placement.clusterOverlap, false);
  assert.equal(placement.nodeOverlap, false);
  assert.equal(placement.ioCount, placement.distances.length);
  assert.equal(placement.inputCount, 0);
  assert.equal(placement.outputCount, 0);
  assert.equal(placement.guardNodeCount, 0);
  assert.equal(placement.failureClusterCount, expectedFailureTransitions);
  assert.equal(placement.failureErrorCount, 0);
  assert(placement.combinedValues.every(value => value.trim().length > 0));
  assert(placement.semanticActions.every(value => value.trim().length === 0), placement.semanticActions.join("\n"));
  assert(placement.combinedValues.every(value => !value.includes(" ➞ ")), placement.combinedValues.join("\n"));
  assert(!placement.combinedValues.some(value => /\b(Idle|Active|Faulted)\b/.test(value)), placement.combinedValues.join("\n"));
  assert(placement.combinedValues.some(value => value.startsWith("? input.legacy_alarm")), placement.combinedValues.join("\n"));
  assert.equal(placement.visibleLegacyLabels, 0);

  await page.click("#glyph-settings");
  await page.selectOption("#glyph-language", "en");
  assert.equal(await page.locator("#compile").count(), 0);
  assert.equal((await page.locator("#save").textContent()).trim(), "Save & Render");
  assert.equal(await page.locator("#save").getAttribute("aria-label"), "Save & Render (Ctrl/Cmd+S)");
  const englishWarnings = await page.locator(".analysis-panel").textContent();
  assert(englishWarnings.includes("provisionally"), englishWarnings);
  await page.waitForFunction(() => document.querySelectorAll('.transition-io-node[data-io-kind="io"]').length > 0);
  await page.click("#glyph-settings-close");

  const beforePan = await page.evaluate(() => {
    const shell = document.querySelector(".canvas-shell");
    const parent = shell.closest(".view-body");
    parent.scrollTop = Math.min(180, Math.max(0, parent.scrollHeight - parent.clientHeight));
    shell.scrollTop = 0;
    return { parent: parent.scrollTop, shell: shell.scrollTop };
  });
  const shellBox = await page.locator(".canvas-shell").boundingBox();
  assert(shellBox);
  const startX = shellBox.x + 20;
  const startY = shellBox.y + 20;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX, startY + 120, { steps: 12 });
  await page.mouse.up();
  const afterPan = await page.evaluate(() => {
    const shell = document.querySelector(".canvas-shell");
    const parent = shell.closest(".view-body");
    return { parent: parent.scrollTop, shell: shell.scrollTop };
  });
  assert(
    afterPan.parent !== beforePan.parent || afterPan.shell !== beforePan.shell,
    `canvas drag did not move either scroll owner: ${JSON.stringify({ beforePan, afterPan })}`,
  );

  assert.deepEqual(browserErrors, [], `browser errors:\n${browserErrors.join("\n")}`);
  await page.screenshot({
    path: path.join(outputDirectory, "localized-provisional-trigger.png"),
    fullPage: false,
  });
  await page.close();
} finally {
  await fs.writeFile(sourcePath, originalSource, "utf8");
  await browser.close();
  await stopProcess(child);
}

console.log("verified localized save-render controls, semantic labels, proximity, and canvas panning");
