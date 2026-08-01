import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

async function waitForServer(url, child, logs) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
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

async function state(page) {
  return page.evaluate(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    const transaction = window.glyphTransitionLayoutTransaction;
    const router = window.glyphInitialTransitionRouter;
    const certificate = window.glyphLayoutPublicationCertificate;
    return {
      layoutState: stage?.dataset.transitionLayoutState || "",
      layoutReason: stage?.dataset.transitionLayoutReason || "",
      layoutError: stage?.dataset.transitionLayoutError || "",
      layoutFailureCode: stage?.dataset.transitionLayoutFailureCode || "",
      layoutFailureDetails: stage?.dataset.transitionLayoutFailureDetails || "",
      collisionSolved: stage?.dataset.transitionIoCollisionSolved || "",
      collisionCount: stage?.dataset.transitionIoCollisionCount || "",
      semanticLines: stage?.dataset.transitionSemanticLinesReady || "",
      semanticRoleLines: stage?.dataset.transitionSemanticRoleLinesReady || "",
      publicationReady: stage?.dataset.transitionPublicationReady || "",
      initialRouteReady: stage?.dataset.initialRouteReady || "",
      initialRouteCertificate: stage?.dataset.initialRouteCertificate || "",
      initialRouteError: stage?.dataset.initialRouteError || "",
      certificateState: stage?.dataset.layoutCertificateState || "",
      certificateRequestState: stage?.dataset.layoutCertificateRequestState || "",
      certificateViolations: stage?.dataset.layoutCertificateViolations || "",
      transactionGeneration: transaction?.generation ?? null,
      transactionCompletedGeneration: transaction?.completedGeneration ?? null,
      routerGeneration: router?.generation ?? null,
      routerCompletedGeneration: router?.completedGeneration ?? null,
      certificateGeneration: certificate?.generation ?? null,
      certificateCompletedGeneration: certificate?.completedGeneration ?? null,
      nodeAdapterVersion: window.glyphTransitionNodePositionAdapter?.version ?? null,
      nodeGuardVersion: window.glyphNodeDragPublicationGuard?.version ?? null,
      persisted: Object.keys(localStorage).some(key => key.startsWith("glyph.diagram.positions.v1:")),
    };
  });
}

async function nodePositions(page) {
  return page.evaluate(() => [...document.querySelectorAll(".state-node")].map(node => ({
    name: node.querySelector(".state-name,.node-name")?.textContent?.trim() || "",
    left: Number.parseFloat(node.style.left || "0") || 0,
    top: Number.parseFloat(node.style.top || "0") || 0,
    selected: node.classList.contains("selected-node"),
  })));
}

async function drag(page, locator, deltaX, deltaY) {
  const box = await locator.boundingBox();
  assert(box, "state node has no bounding box");
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + deltaX, y + deltaY, {steps: 20});
  await page.mouse.up();
}

async function waitForCertified(page, label, minimumGeneration = 0) {
  const samples = [];
  for (let attempt = 0; attempt < 180; attempt += 1) {
    const current = await state(page);
    if (!samples.length || JSON.stringify(current) !== JSON.stringify(samples.at(-1))) {
      samples.push(current);
      console.log(`${label}-state ${JSON.stringify(current)}`);
    }
    if (current.layoutState === "ready"
      && current.collisionSolved === "true"
      && current.collisionCount === "0"
      && current.semanticLines === "true"
      && current.semanticRoleLines === "true"
      && current.publicationReady === "true"
      && current.certificateState === "valid"
      && Number(current.transactionGeneration || 0) >= minimumGeneration
      && current.transactionGeneration === current.transactionCompletedGeneration
      && current.certificateGeneration === current.certificateCompletedGeneration
      && current.persisted) {
      return current;
    }
    await page.waitForTimeout(100);
  }
  throw new Error(`${label} did not converge: ${JSON.stringify(samples.at(-1))}`);
}

const logs = [];
const port = 8898;
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

const browser = await chromium.launch({headless: true});
try {
  const url = `http://127.0.0.1:${port}`;
  await waitForServer(url, child, logs);
  const page = await browser.newPage({viewport: {width: 1500, height: 900}});
  page.on("console", message => console.log(`browser:${message.type()}:${message.text()}`));
  await page.goto(url, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
  if (!await page.locator('button[data-tab="state"]').evaluate(button => button.classList.contains("active"))) {
    await page.click('button[data-tab="state"]');
  }
  await page.waitForFunction(() => {
    const stage = document.querySelector(".state-node")?.closest(".graph-stage");
    return stage?.dataset.transitionLayoutState === "ready"
      && stage.dataset.transitionIoCollisionSolved === "true"
      && stage.dataset.transitionIoCollisionCount === "0"
      && stage.dataset.transitionPublicationReady === "true"
      && stage.dataset.layoutCertificateState === "valid";
  }, undefined, {timeout: 60_000});

  const initial = await state(page);
  assert.equal(initial.nodeAdapterVersion, 6, JSON.stringify(initial));
  assert.equal(initial.nodeGuardVersion, 3, JSON.stringify(initial));
  console.log(`node-drag-before ${JSON.stringify(initial)}`);

  const pointerBefore = await nodePositions(page);
  await drag(page, page.locator(".state-node").first(), 170, 160);
  await page.waitForFunction(before => {
    const node = document.querySelector(".state-node");
    if (!node) return false;
    const left = Number.parseFloat(node.style.left || "0") || 0;
    const top = Number.parseFloat(node.style.top || "0") || 0;
    return Math.abs(left - before.left) > 1 || Math.abs(top - before.top) > 1;
  }, pointerBefore[0], {timeout: 10_000});
  const pointerReady = await waitForCertified(
    page,
    "node-pointer",
    Number(initial.transactionGeneration || 0) + 1,
  );

  const keyboardSetup = await page.evaluate(() => {
    const node = document.querySelector(".state-node.selected-node") || document.querySelector(".state-node");
    const stage = node?.closest(".graph-stage");
    if (!node || !stage) return null;
    node.classList.add("selected-node");
    const left = Number.parseFloat(node.style.left || "0") || 0;
    const top = Number.parseFloat(node.style.top || "0") || 0;
    const width = Number.parseFloat(stage.style.width || "0") || stage.scrollWidth;
    const direction = left + node.offsetWidth + 24 < width ? "ArrowRight" : "ArrowLeft";
    document.activeElement?.blur?.();
    return {left, top, direction};
  });
  assert(keyboardSetup, "keyboard node setup failed");
  await page.keyboard.press(keyboardSetup.direction);
  await page.waitForFunction(before => {
    const node = document.querySelector(".state-node.selected-node");
    if (!node) return false;
    const left = Number.parseFloat(node.style.left || "0") || 0;
    const top = Number.parseFloat(node.style.top || "0") || 0;
    return Math.abs(left - before.left) > 1 || Math.abs(top - before.top) > 1;
  }, keyboardSetup, {timeout: 10_000});
  const keyboardReady = await waitForCertified(
    page,
    "node-keyboard",
    Number(pointerReady.transactionGeneration || 0) + 1,
  );

  const beforeEditorKey = await nodePositions(page);
  const editor = page.locator("#editor");
  assert.equal(await editor.count(), 1, "editor textarea is missing");
  await editor.focus();
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(180);
  const afterEditorKey = await nodePositions(page);
  assert.deepEqual(afterEditorKey, beforeEditorKey, "editor arrow key moved a selected state node");
  const afterEditorState = await state(page);
  assert.equal(afterEditorState.publicationReady, "true", JSON.stringify(afterEditorState));
  assert.equal(
    afterEditorState.transactionGeneration,
    keyboardReady.transactionGeneration,
    "editor arrow key started a layout generation",
  );

  await page.close();
  console.log("verified pointer and keyboard node movement, form-control isolation, persistence, relayout, and recertification");
} finally {
  await browser.close();
  await stopProcess(child);
}
