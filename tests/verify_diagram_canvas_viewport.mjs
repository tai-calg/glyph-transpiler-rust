import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/diagram-canvas-viewport");
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

function startDiagram(file, port, logs) {
  const child = spawn("python3", ["glyph.py", file], {
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
  return child;
}

async function waitForProductionViewport(page) {
  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const shell = stage?.closest(".canvas-shell");
    return document.querySelector(".tab.active")?.dataset.tab === "state"
      && Boolean(stage)
      && Boolean(shell)
      && Boolean(document.querySelector("#diagram-zoom-out"))
      && Boolean(document.querySelector("#diagram-zoom-in"))
      && Boolean(document.querySelector("#diagram-fit"))
      && Boolean(document.querySelector("#diagram-view-reset"))
      && Boolean(stage.dataset.viewportScale)
      && shell.dataset.viewportReady === "true"
      && shell.dataset.touchpadZoomReady === "true"
      && window.glyphDiagramViewport?.version === 2
      && window.glyphDiagramMiddleDragZoom?.version === 1
      && stage.dataset.transitionLayoutState === "ready"
      && stage.dataset.transitionPublicationReady === "true"
      && stage.dataset.transitionIoClustersReady === "true"
      && stage.dataset.transitionLayoutProfile === "ordinary"
      && stage.dataset.stateDiagramWorkspaceGeometryReady === "true"
      && stage.dataset.initialRouteReady === "true"
      && document.querySelectorAll(".transition-index .transition-detail").length > 0
      && !stage.dataset.transitionLayoutError;
  }, null, { timeout: 10_000 });
}

async function waitForStableGeometry(page, timeoutMs = 20_000) {
  const started = Date.now();
  let previous = null;
  let stableSamples = 0;
  while (Date.now() - started < timeoutMs) {
    const current = await page.evaluate(() => {
      const stage = document.querySelector(".graph-stage");
      const shell = document.querySelector(".canvas-shell");
      const node = stage?.querySelector(".state-node");
      if (!stage || !shell || !node) return null;
      return {
        left: Number.parseFloat(node.style.left || "0"),
        top: Number.parseFloat(node.style.top || "0"),
        scrollWidth: shell.scrollWidth,
        scrollHeight: shell.scrollHeight,
        publication: stage.dataset.transitionPublicationReady || "",
        layout: stage.dataset.transitionLayoutState || "",
      };
    });
    if (current && previous) {
      const unchanged = Math.abs(current.left - previous.left) <= 1
        && Math.abs(current.top - previous.top) <= 1
        && Math.abs(current.scrollWidth - previous.scrollWidth) <= 1
        && Math.abs(current.scrollHeight - previous.scrollHeight) <= 1;
      stableSamples = unchanged
        && current.publication === "true"
        && current.layout === "ready"
        ? stableSamples + 1
        : 0;
      if (stableSamples >= 2) return;
    }
    previous = current;
    await page.waitForTimeout(160);
  }
  throw new Error(`production diagram geometry did not settle: ${JSON.stringify(previous)}`);
}

async function viewportAnchor(page, point = null) {
  return page.evaluate(value => {
    const shell = document.querySelector(".canvas-shell");
    const stage = shell?.querySelector(".graph-stage");
    const surface = stage?.parentElement;
    if (!shell || !stage || !surface) return null;
    const clientX = value?.clientX ?? shell.clientWidth * 0.68;
    const clientY = value?.clientY ?? shell.clientHeight * 0.42;
    const scale = Number.parseFloat(stage.dataset.viewportScale || "1");
    const shellRect = shell.getBoundingClientRect();
    return {
      clientX,
      clientY,
      pageX: shellRect.left + clientX,
      pageY: shellRect.top + clientY,
      diagramX: (shell.scrollLeft + clientX - surface.offsetLeft) / scale,
      diagramY: (shell.scrollTop + clientY - surface.offsetTop) / scale,
      scale,
      shellHeight: shell.clientHeight,
    };
  }, point);
}

async function assertAllDiagramElementsVisible(page, label) {
  const audit = await page.evaluate(() => {
    const stage = document.querySelector(".graph-stage");
    const shell = stage?.closest(".canvas-shell");
    if (!stage || !shell) return { ok: false, error: "stage-or-shell-missing" };
    const shellRect = shell.getBoundingClientRect();
    const bounds = {
      left: shellRect.left,
      top: shellRect.top,
      right: shellRect.left + shell.clientWidth,
      bottom: shellRect.top + shell.clientHeight,
    };
    const elements = [
      ...stage.querySelectorAll(".state-node"),
      ...stage.querySelectorAll(".transition-io-cluster"),
    ];
    const outside = elements.map((element, index) => {
      const rect = element.getBoundingClientRect();
      const id = element.dataset.transitionId
        || element.querySelector(".state-name")?.textContent?.trim()
        || `element-${index}`;
      const visible = rect.left >= bounds.left - 2
        && rect.top >= bounds.top - 2
        && rect.right <= bounds.right + 2
        && rect.bottom <= bounds.bottom + 2;
      return visible ? null : { id, left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom };
    }).filter(Boolean);
    return {
      ok: elements.length > 0 && outside.length === 0,
      outside,
      count: elements.length,
      scale: Number.parseFloat(stage.dataset.viewportScale || "1"),
      mode: window.glyphDiagramViewport?.mode?.() || "",
    };
  });
  assert.equal(audit.error, undefined, `${label}: ${audit.error}`);
  assert.equal(audit.ok, true, `${label}: elements escaped viewport: ${JSON.stringify(audit)}`);
  return audit;
}

async function hitTestableStateNode(page) {
  return page.evaluate(() => {
    const nodes = [...document.querySelectorAll(".state-node")];
    const fractions = [0.5, 0.35, 0.65, 0.2, 0.8];
    const rejected = [];
    for (let index = 0; index < nodes.length; index += 1) {
      const node = nodes[index];
      const rect = node.getBoundingClientRect();
      for (const yFraction of fractions) {
        for (const xFraction of fractions) {
          const x = rect.left + rect.width * xFraction;
          const y = rect.top + rect.height * yFraction;
          const hit = document.elementFromPoint(x, y);
          if (hit?.closest?.(".state-node") === node) {
            return {
              index,
              x,
              y,
              nodeName: node.querySelector(".state-name")?.textContent?.trim() || "",
              hitTag: hit.tagName,
              hitClass: hit.className?.baseVal || hit.className || "",
              rect: {
                left: rect.left,
                top: rect.top,
                right: rect.right,
                bottom: rect.bottom,
                width: rect.width,
                height: rect.height,
              },
            };
          }
        }
      }
      const center = document.elementFromPoint(
        rect.left + rect.width / 2,
        rect.top + rect.height / 2,
      );
      rejected.push({
        index,
        nodeName: node.querySelector(".state-name")?.textContent?.trim() || "",
        centerTag: center?.tagName || "",
        centerClass: center?.className?.baseVal || center?.className || "",
        rect: {
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        },
      });
    }
    return { rejected };
  });
}

async function dragNode(page, deltaX, deltaY) {
  const target = await hitTestableStateNode(page);
  assert(
    Number.isInteger(target?.index),
    `no hit-testable state node: ${JSON.stringify(target)}`,
  );
  const node = page.locator(".state-node").nth(target.index);
  const before = await node.evaluate(element => Number.parseFloat(element.style.left));
  const beforeAudit = await node.evaluate((element, point) => {
    const stage = element.closest(".graph-stage");
    const hit = document.elementFromPoint(point.x, point.y);
    return {
      targetIndex: point.index,
      targetName: point.nodeName,
      hitTag: hit?.tagName || "",
      hitClass: hit?.className?.baseVal || hit?.className || "",
      hitNode: hit?.closest?.(".state-node")?.querySelector(".state-name")?.textContent?.trim() || "",
      pointerEvents: getComputedStyle(element).pointerEvents,
      zIndex: getComputedStyle(element).zIndex,
      rect: element.getBoundingClientRect(),
      scale: Number.parseFloat(stage?.dataset.viewportScale || "1"),
      layout: stage?.dataset.transitionLayoutState || "",
      publication: stage?.dataset.transitionPublicationReady || "",
      constrained: stage?.dataset.transitionNodeDragConstrained || "",
    };
  }, target);
  await page.mouse.move(target.x, target.y);
  await page.mouse.down({ button: "left" });
  await page.mouse.move(target.x + deltaX, target.y + deltaY, { steps: 16 });
  await page.mouse.up({ button: "left" });
  const afterAudit = await node.evaluate(element => {
    const stage = element.closest(".graph-stage");
    return {
      left: Number.parseFloat(element.style.left),
      selected: element.classList.contains("selected-node"),
      dragging: element.classList.contains("dragging"),
      constrained: stage?.dataset.transitionNodeDragConstrained || "",
      positions: stage?.dataset.transitionNodePositions || "",
      publication: stage?.dataset.transitionPublicationReady || "",
      layout: stage?.dataset.transitionLayoutState || "",
    };
  });
  return { movement: afterAudit.left - before, before, beforeAudit, afterAudit };
}

async function verifyViewportControls(browser) {
  const logs = [];
  const port = 8896;
  const child = startDiagram("examples/state_diagrams/conveyor_control.glyph", port, logs);
  try {
    const url = `http://127.0.0.1:${port}`;
    await waitForServer(url, child, logs);
    const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.stack || error.message));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    await page.goto(url, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
    await page.click('button[data-tab="state"]');
    await waitForProductionViewport(page);
    await waitForStableGeometry(page);

    await page.click("#diagram-fit");
    await page.waitForFunction(() => window.glyphDiagramViewport?.mode?.() === "fit");
    await page.waitForTimeout(200);
    await assertAllDiagramElementsVisible(page, "conveyor initial fit");

    await page.click("#diagram-view-reset");
    await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.viewportScale === "1");
    assert.equal(await page.locator("#diagram-zoom-value").textContent(), "100%");

    await page.click("#diagram-zoom-out");
    await page.click("#diagram-zoom-out");
    await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.viewportScale === "0.8");
    assert.equal(await page.locator("#diagram-zoom-value").textContent(), "80%");
    const drag = await dragNode(page, 80, 0);
    assert(Math.abs(drag.movement - 100) <= 10, `zoom-aware drag diagnostics: ${JSON.stringify(drag)}`);
    await waitForStableGeometry(page);

    await page.click("#diagram-view-reset");
    await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.viewportScale === "1");
    const before = await viewportAnchor(page);
    assert(before, "missing pinch anchor");
    await page.locator(".canvas-shell").dispatchEvent("wheel", {
      deltaY: -160,
      deltaMode: 0,
      ctrlKey: true,
      clientX: before.pageX,
      clientY: before.pageY,
    });
    await page.waitForFunction(() => Number.parseFloat(
      document.querySelector(".graph-stage")?.dataset.viewportScale || "1"
    ) > 1);
    await page.waitForTimeout(160);
    const after = await viewportAnchor(page, before);
    assert(after.scale > before.scale, "touchpad pinch did not zoom in");
    assert(Math.abs(after.shellHeight - before.shellHeight) < 2, "pinch resized viewport");
    assert(Math.abs(after.diagramX - before.diagramX) < 3, "pinch changed x anchor");
    assert(Math.abs(after.diagramY - before.diagramY) < 3, "pinch changed y anchor");

    const shell = page.locator(".canvas-shell");
    const shellBox = await shell.boundingBox();
    assert(shellBox, "canvas shell has no bounding box");
    const scaleBeforeMiddle = Number.parseFloat(await page.locator(".graph-stage").getAttribute("data-viewport-scale"));
    const x = shellBox.x + shellBox.width * 0.55;
    const y = shellBox.y + shellBox.height * 0.55;
    await page.mouse.move(x, y);
    await page.mouse.down({ button: "middle" });
    await page.mouse.move(x, y - 70, { steps: 12 });
    await page.mouse.up({ button: "middle" });
    await page.waitForFunction(previous => (
      Number.parseFloat(document.querySelector(".graph-stage")?.dataset.viewportScale || "1") > previous
      && document.querySelector(".canvas-shell")?.dataset.middleDragZoomState === "idle"
    ), scaleBeforeMiddle);

    await page.click("#diagram-fit");
    await page.waitForFunction(() => window.glyphDiagramViewport?.mode?.() === "fit");
    await page.waitForTimeout(200);
    const fitted = await assertAllDiagramElementsVisible(page, "conveyor explicit fit");
    assert(fitted.scale >= 0.25 && fitted.scale <= 3);
    assert.deepEqual(errors, [], `viewport emitted browser errors:\n${errors.join("\n")}`);

    await page.screenshot({ path: path.join(outputDirectory, "conveyor-viewport-controls.png"), fullPage: true });
    await page.close();
  } finally {
    await stopProcess(child);
  }
}

async function verifyDiagnosticsFit(browser) {
  const logs = [];
  const port = 8897;
  const child = startDiagram("examples/state_diagrams/traffic_light.glyph", port, logs);
  try {
    const url = `http://127.0.0.1:${port}`;
    await waitForServer(url, child, logs);
    const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.stack || error.message));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    await page.goto(url, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
    await page.click('button[data-tab="state"]');
    await waitForProductionViewport(page);
    await waitForStableGeometry(page);
    assert.equal(await page.locator(".analysis-code").count(), 4);
    await page.click("#diagram-fit");
    await page.waitForFunction(() => window.glyphDiagramViewport?.mode?.() === "fit");
    await page.waitForTimeout(200);
    await assertAllDiagramElementsVisible(page, "traffic diagnostics fit");
    assert.deepEqual(errors, [], `traffic viewport emitted browser errors:\n${errors.join("\n")}`);
    await page.screenshot({ path: path.join(outputDirectory, "traffic-diagnostics-fit.png"), fullPage: true });
    await page.close();
  } finally {
    await stopProcess(child);
  }
}

const browser = await chromium.launch({ headless: true });
try {
  await verifyViewportControls(browser);
  await verifyDiagnosticsFit(browser);
} finally {
  await browser.close();
}

console.log("verified production zoom, fit/reset, anchor-preserving pinch, middle-drag zoom, and viewport visibility");
