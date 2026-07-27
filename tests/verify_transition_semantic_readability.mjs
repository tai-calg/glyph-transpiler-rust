import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const cases = [
  {
    slug: "conveyor",
    file: "examples/state_diagrams/conveyor_control.glyph",
    machine: "Conveyor",
    dense: true,
    required: "ConveyorStop ➞ set_conveyor(0.0)",
  },
  {
    slug: "traffic-light",
    file: "examples/state_diagrams/traffic_light.glyph",
    machine: "Traffic",
    dense: true,
  },
  {
    slug: "session-protocol",
    file: "examples/state_diagrams/session_protocol.glyph",
    machine: "Session",
    dense: true,
  },
];

const outputDirectory = path.resolve("build/transition-semantic-readability");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 180; attempt += 1) {
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

async function inspect(page) {
  return page.evaluate(() => {
    const stage = document.querySelector(".graph-stage");
    const stageRect = stage?.getBoundingClientRect();
    const nodes = [...stage.querySelectorAll(".state-node")].map(node => node.getBoundingClientRect());
    const overlaps = (left, right, gap = 1) => !(
      left.right <= right.left + gap || right.right <= left.left + gap
      || left.bottom <= right.top + gap || right.bottom <= left.top + gap
    );
    const labels = [...stage.querySelectorAll(".transition-io-cluster")].map(cluster => {
      const node = cluster.querySelector(".transition-io-node.io");
      const value = cluster.querySelector(".transition-io-value");
      const nodeRect = node.getBoundingClientRect();
      const lines = [...value.querySelectorAll(":scope > .transition-semantic-line")].map(line => {
        const rect = line.getBoundingClientRect();
        const style = getComputedStyle(line);
        return {
          text: line.textContent || "",
          whiteSpace: style.whiteSpace,
          inside: rect.left >= nodeRect.left - 1.5 && rect.right <= nodeRect.right + 1.5,
          width: rect.width,
          nodeWidth: nodeRect.width,
        };
      });
      return {
        id: cluster.dataset.transitionId,
        text: value.textContent || "",
        semantic: cluster.dataset.ioValue || "",
        lineCount: Number(cluster.dataset.semanticLineCount || 0),
        longest: Number(cluster.dataset.semanticLongestLine || 0),
        fallback: cluster.dataset.semanticLineFallback || "",
        distance: Number(cluster.dataset.ioDistance || 0),
        rect: cluster.getBoundingClientRect(),
        lines,
      };
    });
    const collisions = [];
    labels.forEach((label, index) => {
      labels.slice(index + 1).forEach(other => {
        if (overlaps(label.rect, other.rect)) collisions.push(`${label.id}/${other.id}`);
      });
      nodes.forEach((node, nodeIndex) => {
        if (overlaps(label.rect, node)) collisions.push(`${label.id}/node-${nodeIndex}`);
      });
    });
    const outside = stageRect ? labels.filter(label => (
      label.rect.left < stageRect.left - 1 || label.rect.top < stageRect.top - 1
      || label.rect.right > stageRect.right + 1 || label.rect.bottom > stageRect.bottom + 1
    )).map(label => label.id) : ["missing-stage"];
    return {
      stageReady: stage?.dataset.transitionSemanticLinesReady,
      denseLayout: stage?.dataset.semanticDenseLayout || "",
      collisionState: stage?.dataset.transitionIoCollisionSolved || "",
      collisionCount: Number(stage?.dataset.transitionIoCollisionCount || 0),
      labels,
      collisions,
      outside,
    };
  });
}

const browser = await chromium.launch({ headless: true });
try {
  let port = 8920;
  for (const testCase of cases) {
    const logs = [];
    const child = spawn("python3", ["glyph.py", testCase.file], {
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

    try {
      const url = `http://127.0.0.1:${port}`;
      await waitForServer(url, child, logs);
      const page = await browser.newPage({ viewport: { width: 1900, height: 1200 } });
      await page.goto(url, { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
      if (!await page.locator('button[data-tab="state"]').evaluate(button => button.classList.contains("active"))) {
        await page.click('button[data-tab="state"]');
      }
      await page.selectOption("#machine-select", { label: testCase.machine });
      await page.waitForFunction(machine => {
        const stage = document.querySelector(".graph-stage");
        const layout = stage?.dataset.transitionIoCollisionSolved;
        return document.querySelector("#machine-select")?.selectedOptions?.[0]?.textContent === machine
          && stage?.dataset.transitionIoClustersReady === "true"
          && stage?.dataset.transitionSemanticLinesReady === "true"
          && (layout === "true" || layout === "fallback")
          && Number(stage.dataset.transitionIoCollisionCount || 0) === 0
          && [...stage.querySelectorAll(".transition-io-cluster")].every(cluster => (
            cluster.querySelectorAll(".transition-semantic-line").length > 0
          ));
      }, testCase.machine, { timeout: 15000 });
      await page.waitForTimeout(300);

      const result = await inspect(page);
      assert.equal(result.stageReady, "true", `${testCase.slug}: semantic layout not ready`);
      assert(["true", "fallback"].includes(result.collisionState), `${testCase.slug}: collision state ${result.collisionState}`);
      assert.equal(result.collisionCount, 0, `${testCase.slug}: unresolved collision count`);
      assert.equal(Boolean(result.denseLayout), testCase.dense, `${testCase.slug}: dense layout decision`);
      assert(result.labels.length > 0, `${testCase.slug}: no labels`);
      assert(result.labels.every(label => label.text === label.semantic), `${testCase.slug}: visible label differs from semantic value`);
      assert(result.labels.every(label => label.fallback === ""), `${testCase.slug}: semantic line fallback used`);
      assert(result.labels.every(label => label.lineCount === label.lines.length && label.lineCount > 0));
      assert(result.labels.every(label => label.lines.every(line => line.whiteSpace === "nowrap")));
      assert(result.labels.every(label => label.lines.every(line => line.inside)), `${testCase.slug}: line escaped label box`);
      assert(result.labels.every(label => label.lines.every(line => line.text.trim().length >= 4)), `${testCase.slug}: character-fragmented line`);
      assert(result.labels.every(label => label.distance <= 96.5), `${testCase.slug}: label escaped arrow tether`);
      assert.deepEqual(result.collisions, [], `${testCase.slug}: label collision`);
      assert.deepEqual(result.outside, [], `${testCase.slug}: label outside stage`);
      if (testCase.required) {
        assert(result.labels.some(label => label.text === testCase.required), result.labels.map(label => label.text).join("\n"));
      }

      const exported = await page.evaluate(() => {
        const markup = window.glyphReadableDiagramExports.svg();
        const documentValue = new DOMParser().parseFromString(markup, "image/svg+xml");
        return [...documentValue.querySelectorAll(".transition-io-export-label")].map(group => ({
          full: group.getAttribute("data-full-label") || "",
          lines: [...group.querySelectorAll("tspan")].map(line => line.textContent || ""),
        }));
      });
      assert.deepEqual(exported.map(item => item.full), result.labels.map(label => label.text), `${testCase.slug}: SVG full labels differ`);
      assert(exported.every((item, index) => item.lines.length === result.labels[index].lines.length), `${testCase.slug}: SVG line structure differs`);

      await page.screenshot({
        path: path.join(outputDirectory, `${testCase.slug}.png`),
        fullPage: true,
      });
      await page.close();
    } finally {
      await stopProcess(child);
      port += 1;
    }
  }
} finally {
  await browser.close();
}

console.log("verified semantic transition labels without clipping or character fragmentation");
