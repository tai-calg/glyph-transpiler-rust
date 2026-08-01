import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/label-identifier-interactions");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 180; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph process exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`, { cache: "no-store" });
      if (response.ok && (await response.json()).status === "ready") return;
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

async function drag(page, locator, deltaX, deltaY) {
  const box = await locator.boundingBox();
  assert(box, "transition label has no bounding box");
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + deltaX, y + deltaY, { steps: 10 });
  await page.mouse.up();
}

async function interactableLabelIndex(page) {
  return page.evaluate(() => {
    const clusters = [...document.querySelectorAll(".transition-io-cluster")];
    const candidates = clusters.map((cluster, index) => {
      const rect = cluster.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top + rect.height / 2;
      const hit = x >= 0 && x < innerWidth && y >= 0 && y < innerHeight
        ? document.elementFromPoint(x, y)?.closest?.(".transition-io-cluster")
        : null;
      return {
        index,
        length: (cluster.dataset.ioValue || "").length,
        interactable: hit === cluster,
      };
    });
    return candidates
      .filter(candidate => candidate.interactable)
      .sort((a, b) => b.length - a.length || a.index - b.index)[0]?.index ?? -1;
  });
}

const logs = [];
const browserErrors = [];
const port = 8901;
const child = spawn("python3", ["glyph.py", "examples/state_diagrams/conveyor_control.glyph"], {
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
  const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  await page.waitForFunction(() => window.glyphEditorIdentifierHighlight?.version === 2);

  const candidate = await page.evaluate(() => {
    const editor = document.getElementById("editor");
    const counts = new Map();
    const ignored = new Set(["System", "Machine", "State", "Effect", "Type", "true", "false", "otherwise"]);
    for (const match of editor.value.matchAll(/[A-Za-z_][A-Za-z0-9_]*/g)) {
      if (ignored.has(match[0]) || match[0].length < 3) continue;
      const row = counts.get(match[0]) || { token: match[0], count: 0, indexes: [] };
      row.count += 1;
      row.indexes.push(match.index);
      counts.set(match[0], row);
    }
    return [...counts.values()].sort((a, b) => b.count - a.count || b.token.length - a.token.length)
      .find(row => row.count >= 2) || null;
  });
  assert(candidate, "source does not contain a repeated identifier");

  await page.evaluate(({ token, indexes }) => {
    const editor = document.getElementById("editor");
    editor.focus();
    editor.setSelectionRange(indexes[0], indexes[0] + token.length);
    editor.dispatchEvent(new Event("select", { bubbles: true }));
  }, candidate);
  await page.waitForFunction(({ token, count }) => {
    const editor = document.getElementById("editor");
    return editor.dataset.activeIdentifier === token
      && Number(editor.dataset.identifierMatchCount || 0) === count
      && document.querySelectorAll("#identifier-highlight-layer mark").length === count;
  }, candidate);

  const selectionResult = await page.evaluate(() => ({
    identifier: window.glyphEditorIdentifierHighlight.identifier(),
    matchCount: window.glyphEditorIdentifierHighlight.matchCount(),
    layerIdentifier: document.querySelector(".identifier-highlight-surface")?.dataset.identifier || "",
    active: document.querySelector(".editor-wrap")?.classList.contains("identifier-highlight-active") || false,
  }));
  assert.equal(selectionResult.identifier, candidate.token);
  assert.equal(selectionResult.matchCount, candidate.count);
  assert.equal(selectionResult.layerIdentifier, candidate.token);
  assert.equal(selectionResult.active, true);

  await page.evaluate(({ token, indexes }) => {
    const editor = document.getElementById("editor");
    const caret = indexes[1] + Math.min(1, token.length - 1);
    editor.focus();
    editor.setSelectionRange(caret, caret);
    editor.dispatchEvent(new Event("select", { bubbles: true }));
  }, candidate);
  await page.waitForFunction(token => (
    document.getElementById("editor")?.dataset.activeIdentifier === token
  ), candidate.token);

  await page.click('button[data-tab="state"]');
  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return stage?.dataset.transitionLayoutState === "ready"
      && stage?.dataset.transitionIoClustersReady === "true"
      && document.querySelectorAll(".transition-io-cluster").length > 0
      && window.glyphTransitionLabelInspector?.version === 1
      && !document.querySelector(".editor-wrap")?.classList.contains("identifier-highlight-active");
  }, { timeout: 60_000 });

  const labelIndex = await interactableLabelIndex(page);
  assert(labelIndex >= 0, "no transition label is physically interactable");
  const label = page.locator(".transition-io-cluster").nth(labelIndex);
  const expectedLabel = await label.evaluate(element => ({
    id: element.dataset.transitionId || "",
    fullText: element.dataset.ioValue || "",
    status: element.dataset.rtaiSemanticStatus || "unknown",
    reason: element.dataset.rtaiSemanticReason || "",
  }));
  assert(expectedLabel.fullText, "transition label has no canonical full text");

  await label.dblclick();
  await page.waitForFunction(({ id, fullText }) => {
    const panel = document.querySelector(".transition-label-inspector:not([hidden])");
    return panel?.dataset.transitionId === id && panel?.dataset.fullText === fullText;
  }, expectedLabel);
  const inspector = await page.locator(".transition-label-inspector:not([hidden])").evaluate(panel => ({
    fullText: panel.querySelector(".transition-label-inspector-full")?.textContent || "",
    bodyText: panel.textContent || "",
  }));
  assert.equal(inspector.fullText, expectedLabel.fullText);
  if (expectedLabel.status === "unknown") {
    assert(inspector.bodyText.includes("Unknown（解析未確定）"));
    if (expectedLabel.reason) assert(inspector.bodyText.includes(expectedLabel.reason));
  }
  await page.keyboard.press("Escape");
  assert.equal(await page.locator(".transition-label-inspector:not([hidden])").count(), 0);

  const deltas = [[24, 0], [-24, 0], [0, 24], [0, -24], [18, 18], [-18, 18], [18, -18], [-18, -18]];
  let dragResult = null;
  for (const [dx, dy] of deltas) {
    const before = await label.evaluate(element => ({
      left: Number.parseFloat(element.style.left || "0") || 0,
      top: Number.parseFloat(element.style.top || "0") || 0,
    }));
    await drag(page, label, dx, dy);
    await page.waitForTimeout(350);
    const after = await label.evaluate(element => ({
      left: Number.parseFloat(element.style.left || "0") || 0,
      top: Number.parseFloat(element.style.top || "0") || 0,
      state: element.dataset.manualIoGestureState || "",
      manual: element.dataset.manualIo || "",
      rejected: element.dataset.manualIoRejected || "",
    }));
    if (after.state === "persisted" && after.manual === "true"
      && (Math.abs(after.left - before.left) > 1 || Math.abs(after.top - before.top) > 1)) {
      dragResult = { before, after, dx, dy };
      break;
    }
  }
  assert(dragResult, "transition label could not be moved to a persisted valid position");

  await page.screenshot({ path: path.join(outputDirectory, "interactions.png"), fullPage: true });
  await fs.writeFile(path.join(outputDirectory, "report.json"), `${JSON.stringify({
    identifier: candidate.token,
    identifier_match_count: candidate.count,
    label_transition_id: expectedLabel.id,
    label_full_text_length: expectedLabel.fullText.length,
    label_status: expectedLabel.status,
    drag: dragResult,
  }, null, 2)}\n`);
  assert.deepEqual(browserErrors, [], browserErrors.join("\n"));
  console.log(JSON.stringify({
    identifier: candidate.token,
    identifierMatchCount: candidate.count,
    labelTransitionId: expectedLabel.id,
    labelFullTextLength: expectedLabel.fullText.length,
    labelMoved: true,
  }));
} finally {
  await browser.close();
  await stopProcess(child);
}
