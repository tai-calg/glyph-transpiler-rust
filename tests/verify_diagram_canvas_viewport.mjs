import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/diagram-canvas-viewport");
await fs.mkdir(outputDirectory, { recursive: true });

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 160; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`Glyph process exited early\n${logs.join("")}`);
    }
    try {
      const response = await fetch(`${url}/api/state`);
      if (response.ok && (await response.json()).status === "ready") return;
    } catch {
      // The server is still starting.
    }
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

async function drag(page, locator, deltaX, deltaY) {
  const before = await locator.boundingBox();
  assert(before, "drag target has no bounding box");
  const startX = before.x + before.width / 2;
  const startY = before.y + before.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + deltaX, startY + deltaY, { steps: 16 });
  await page.mouse.up();
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
      scrollLeft: shell.scrollLeft,
      scrollTop: shell.scrollTop,
      surfaceLeft: surface.offsetLeft,
      surfaceTop: surface.offsetTop,
      shellWidth: shell.clientWidth,
      shellHeight: shell.clientHeight,
      scrollWidth: shell.scrollWidth,
      scrollHeight: shell.scrollHeight,
    };
  }, point);
}

async function waitForPublicationReady(page, { requireFitVisibility = true } = {}) {
  await page.waitForFunction(requireVisibility => {
    const stage = document.querySelector(".graph-stage");
    if (!stage) return false;
    const visibilityReady = !requireVisibility || stage.dataset.fitVisibilityState === "ready";
    return stage.dataset.transitionLayoutState === "ready"
      && stage.dataset.transitionPublicationReady === "true"
      && stage.dataset.layoutCertificateState === "valid"
      && stage.dataset.renderStable === "true"
      && stage.dataset.transitionIoClustersReady === "true"
      && stage.dataset.transitionIoCollisionSolved === "true"
      && stage.dataset.transitionIoCollisionCount === "0"
      && visibilityReady;
  }, requireFitVisibility, { timeout: 60_000 });
}

async function waitForStableDiagramGeometry(page, timeoutMs = 16000) {
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
        collision: stage.dataset.transitionIoCollisionSolved || "",
        publication: stage.dataset.transitionPublicationReady || "",
        certificate: stage.dataset.layoutCertificateState || "",
        visibility: stage.dataset.fitVisibilityState || "",
      };
    });
    if (current && previous) {
      const unchanged = (
        Math.abs(current.left - previous.left) <= 1
        && Math.abs(current.top - previous.top) <= 1
        && Math.abs(current.scrollWidth - previous.scrollWidth) <= 1
        && Math.abs(current.scrollHeight - previous.scrollHeight) <= 1
      );
      const certified = current.collision === "true"
        && current.publication === "true"
        && current.certificate === "valid";
      stableSamples = unchanged && certified ? stableSamples + 1 : 0;
      if (stableSamples >= 2) return current;
    }
    previous = current;
    await page.waitForTimeout(160);
  }
  throw new Error(`diagram geometry did not settle: ${JSON.stringify(previous)}`);
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
      const fullyVisible = rect.left >= bounds.left - 2
        && rect.top >= bounds.top - 2
        && rect.right <= bounds.right + 2
        && rect.bottom <= bounds.bottom + 2;
      return fullyVisible ? null : {
        id,
        rect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom },
      };
    }).filter(Boolean);
    return {
      ok: outside.length === 0 && elements.length > 0,
      outside,
      count: elements.length,
      bounds,
      scale: Number.parseFloat(stage.dataset.viewportScale || "1"),
      fitVisibilityState: stage.dataset.fitVisibilityState || "",
      fitVisibilityDetails: stage.dataset.fitVisibilityDetails || "",
      shell: { width: shell.clientWidth, height: shell.clientHeight },
      stage: { width: stage.scrollWidth, height: stage.scrollHeight },
    };
  });
  assert.equal(audit.error, undefined, `${label}: ${audit.error}`);
  assert.equal(audit.ok, true, `${label}: diagram elements escaped the viewport: ${JSON.stringify(audit)}`);
  return audit;
}

async function verifyViewportControls(browser) {
  const logs = [];
  const port = 8896;
  const child = startDiagram("examples/state_diagrams/conveyor_control.glyph", port, logs);
  try {
    const url = `http://127.0.0.1:${port}`;
    await waitForServer(url, child, logs);
    const page = await browser.newPage({ viewport: { width: 1500, height: 900 } });
    await page.goto(url, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
    await page.click('button[data-tab="state"]');
    await page.waitForFunction(() => (
      document.querySelector("#diagram-zoom-out")
      && document.querySelector("#diagram-zoom-in")
      && document.querySelector("#diagram-fit")
      && document.querySelector("#diagram-view-reset")
      && document.querySelector(".graph-stage")?.dataset.viewportScale
      && document.querySelector(".canvas-shell")?.dataset.touchpadZoomReady === "true"
      && window.glyphDiagramFitStability?.version === 1
    ));
    await waitForPublicationReady(page);
    await waitForStableDiagramGeometry(page);
    await assertAllDiagramElementsVisible(page, "conveyor initial fit");

    assert.equal(await page.locator(".canvas-pan-help").count(), 0);
    assert.equal(await page.locator(".canvas-shell").getAttribute("title"), null);

    await page.click("#diagram-view-reset");
    await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.viewportScale === "1");
    assert.equal(await page.locator("#diagram-zoom-value").textContent(), "100%");

    await page.click("#diagram-zoom-out");
    await page.click("#diagram-zoom-out");
    await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.viewportScale === "0.8");
    assert.equal(await page.locator("#diagram-zoom-value").textContent(), "80%");

    const node = page.locator(".state-node").first();
    const beforeLeft = await node.evaluate(element => Number.parseFloat(element.style.left));
    await drag(page, node, 80, 0);
    const afterLeft = await node.evaluate(element => Number.parseFloat(element.style.left));
    assert(
      Math.abs((afterLeft - beforeLeft) - 100) <= 8,
      `zoom-aware node drag moved ${afterLeft - beforeLeft}px instead of about 100px`,
    );
    await waitForStableDiagramGeometry(page);

    await page.click("#diagram-view-reset");
    await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.viewportScale === "1");
    await waitForStableDiagramGeometry(page);
    const anchorBefore = await viewportAnchor(page);
    assert(anchorBefore, "missing viewport anchor before pinch");
    await page.locator(".canvas-shell").dispatchEvent("wheel", {
      deltaY: -160,
      deltaMode: 0,
      ctrlKey: true,
      clientX: anchorBefore.pageX,
      clientY: anchorBefore.pageY,
    });
    await page.waitForFunction(() => Number.parseFloat(
      document.querySelector(".graph-stage")?.dataset.viewportScale || "1"
    ) > 1);
    await page.waitForTimeout(160);
    const anchorAfterZoomIn = await viewportAnchor(page, {
      clientX: anchorBefore.clientX,
      clientY: anchorBefore.clientY,
    });
    const anchorDiagnostics = `before=${JSON.stringify(anchorBefore)} after=${JSON.stringify(anchorAfterZoomIn)}`;
    assert(anchorAfterZoomIn.scale > anchorBefore.scale, `touchpad pinch did not zoom in; ${anchorDiagnostics}`);
    assert(Math.abs(anchorAfterZoomIn.shellHeight - anchorBefore.shellHeight) < 2, `pinch resized the canvas viewport; ${anchorDiagnostics}`);
    assert(Math.abs(anchorAfterZoomIn.diagramX - anchorBefore.diagramX) < 3, `pinch changed the x anchor; ${anchorDiagnostics}`);
    assert(Math.abs(anchorAfterZoomIn.diagramY - anchorBefore.diagramY) < 3, `pinch changed the y anchor; ${anchorDiagnostics}`);

    await page.locator(".canvas-shell").dispatchEvent("wheel", {
      deltaY: 160,
      deltaMode: 0,
      ctrlKey: true,
      clientX: anchorBefore.pageX,
      clientY: anchorBefore.pageY,
    });
    await page.waitForFunction(previous => (
      Number.parseFloat(document.querySelector(".graph-stage")?.dataset.viewportScale || "1") < previous
    ), anchorAfterZoomIn.scale);
    await page.waitForTimeout(80);
    const anchorAfterZoomOut = await viewportAnchor(page, {
      clientX: anchorBefore.clientX,
      clientY: anchorBefore.clientY,
    });
    assert(anchorAfterZoomOut.scale < anchorAfterZoomIn.scale, "touchpad pinch did not zoom out");
    assert(Math.abs(anchorAfterZoomOut.shellHeight - anchorBefore.shellHeight) < 2, "pinch out resized the canvas viewport");

    await page.click("#diagram-fit");
    await page.waitForFunction(() => window.glyphDiagramViewport?.mode?.() === "fit");
    await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.fitVisibilityState === "ready");
    const fitted = await assertAllDiagramElementsVisible(page, "conveyor explicit fit");
    assert(fitted.scale >= 0.25 && fitted.scale <= 3);

    await page.click("#diagram-view-reset");
    await page.waitForFunction(() => document.querySelector(".graph-stage")?.dataset.viewportScale === "1");
    assert.equal(await page.locator("#diagram-zoom-value").textContent(), "100%");

    await page.screenshot({
      path: path.join(outputDirectory, "conveyor-viewport-controls.png"),
      fullPage: true,
    });
    await page.close();
  } finally {
    await stopProcess(child);
  }
}

async function verifyDiagnosticsResizeVisibility(browser) {
  const logs = [];
  const port = 8897;
  const child = startDiagram("examples/state_diagrams/traffic_light.glyph", port, logs);
  try {
    const url = `http://127.0.0.1:${port}`;
    await waitForServer(url, child, logs);
    const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
    const browserErrors = [];
    page.on("pageerror", error => browserErrors.push(error.stack || error.message));
    page.on("console", message => {
      if (message.type() === "error") browserErrors.push(message.text());
    });
    await page.goto(url, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
    await page.click('button[data-tab="state"]');
    await waitForPublicationReady(page);
    await waitForStableDiagramGeometry(page);

    const warnings = await page.locator(".analysis-code").allTextContents();
    assert.equal(warnings.length, 4, `traffic diagnostics did not render four warnings: ${warnings}`);
    const audit = await assertAllDiagramElementsVisible(page, "traffic diagnostics resize");
    assert(audit.scale >= 0.25, `traffic fit scale fell below supported minimum: ${audit.scale}`);
    assert.equal(
      await page.locator(".graph-stage").getAttribute("data-fit-visibility-state"),
      "ready",
    );
    assert.deepEqual(browserErrors, [], `traffic viewport emitted browser errors:\n${browserErrors.join("\n")}`);

    await page.screenshot({
      path: path.join(outputDirectory, "traffic-diagnostics-fit-visibility.png"),
      fullPage: true,
    });
    await page.close();
  } finally {
    await stopProcess(child);
  }
}

const browser = await chromium.launch({ headless: true });
try {
  await verifyViewportControls(browser);
  await verifyDiagnosticsResizeVisibility(browser);
} finally {
  await browser.close();
}

console.log("verified touchpad zoom, fit/reset controls, zoom-aware dragging, and full diagram visibility after diagnostics resizing");
