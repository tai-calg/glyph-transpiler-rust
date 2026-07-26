import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/localized-semantic-canvas");
await fs.mkdir(outputDirectory, { recursive: true });
const sourcePath = path.join(outputDirectory, "provisional-trigger.glyph");
await fs.writeFile(sourcePath, `+Mode=Idle|Active|Faulted
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
`, "utf8");

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 160; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Glyph process exited early\n${logs.join("")}`);
    try {
      const response = await fetch(`${url}/api/state`);
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
  await waitForServer(url, child, logs);
  const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelector("#status")?.classList.contains("ready"));
  await page.waitForFunction(() => (
    document.querySelector(".graph-stage")?.dataset.labelEditorReady === "true"
    && document.querySelector(".graph-stage")?.dataset.stateTransitionIRV3LabelsReady === "true"
    && document.querySelector("#glyph-settings")
  ));

  assert.equal((await page.locator("#compile").textContent()).trim(), "コンパイル");
  assert.equal(await page.locator("html").getAttribute("lang"), "ja");
  const japaneseWarnings = await page.locator(".analysis-panel").textContent();
  assert(japaneseWarnings.includes("暫定的に入力"), japaneseWarnings);

  const detailText = await page.locator(".transition-detail-id").allTextContents();
  assert(detailText.some(value => value.includes("Start [input.allowed]")), detailText.join("\n"));
  assert(detailText.some(value => value.includes("? input.legacy_alarm")), detailText.join("\n"));
  assert(!detailText.some(value => value.includes("[input.legacy_alarm]")), detailText.join("\n"));

  const placement = await page.evaluate(() => {
    const labels = [...document.querySelectorAll(".transition-label")];
    const nodes = [...document.querySelectorAll(".state-node")];
    const overlaps = (a, b, gap = 2) => !(
      a.right + gap <= b.left || b.right + gap <= a.left
      || a.bottom + gap <= b.top || b.bottom + gap <= a.top
    );
    const labelRects = labels.map(label => label.getBoundingClientRect());
    const nodeRects = nodes.map(node => node.getBoundingClientRect());
    return {
      distances: labels.map(label => Number(label.dataset.labelDistance || 0)),
      labelOverlap: labelRects.some((rect, index) => labelRects.slice(index + 1).some(other => overlaps(rect, other))),
      nodeOverlap: labelRects.some(rect => nodeRects.some(node => overlaps(rect, node))),
    };
  });
  assert(placement.distances.length > 0);
  assert(placement.distances.every(value => value <= 96.5), placement.distances.join(", "));
  assert.equal(placement.labelOverlap, false);
  assert.equal(placement.nodeOverlap, false);

  await page.click("#glyph-settings");
  await page.selectOption("#glyph-language", "en");
  assert.equal((await page.locator("#compile").textContent()).trim(), "Compile");
  const englishWarnings = await page.locator(".analysis-panel").textContent();
  assert(englishWarnings.includes("provisionally"), englishWarnings);
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

  await page.screenshot({
    path: path.join(outputDirectory, "localized-provisional-trigger.png"),
    fullPage: false,
  });
  await page.close();
} finally {
  await browser.close();
  await stopProcess(child);
}

console.log("verified Japanese-first diagnostics, semantic labels, proximity and canvas panning");
