import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const outputDirectory = path.resolve("build/save-triggered-studio");
await fs.mkdir(outputDirectory, { recursive: true });
const sourcePath = path.join(outputDirectory, "save-triggered.glyph");
const initialSource = "@MAX 10\n>value():I=MAX\n";
await fs.writeFile(sourcePath, initialSource, "utf8");

const port = 8893;
const url = `http://127.0.0.1:${port}`;
const logs = [];

async function waitForServer(child) {
  for (let attempt = 0; attempt < 160; attempt += 1) {
    if (child.exitCode !== null) {
      throw new Error(`Glyph process exited early\n${logs.join("")}`);
    }
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

async function audit(page) {
  return page.evaluate(() => ({
    source: snapshot?.source ?? null,
    snapshotStatus: snapshot?.status ?? null,
    version: Number(snapshot?.version || 0),
    operationId: snapshot?.operation_id || "",
    digest: snapshot?.digest || "",
    renderedDigest: snapshot?.rendered_digest || "",
    editorSource: document.querySelector("#editor")?.value || "",
    statusText: document.querySelector("#status")?.textContent || "",
    persistence: document.querySelector("#glyph-save-state")?.dataset.persistence || "",
    renderState: document.querySelector("#glyph-save-state")?.dataset.render || "",
    saveInFlight: window.GlyphSaveTriggeredRendering?.saveInFlight ?? null,
    activeSaveRequestId: window.GlyphSaveTriggeredRendering?.activeSaveRequestId || "",
    baseDigest: window.GlyphSaveTriggeredRendering?.baseDigest || "",
    conflict: window.GlyphSaveTriggeredRendering?.conflict || null,
    conflictOpen: Boolean(document.querySelector("#glyph-conflict-dialog")?.open),
    staleVisible: document.querySelector("#glyph-stale-banner")?.hidden === false,
    staleText: document.querySelector("#glyph-stale-banner")?.textContent || "",
    saveDisabled: Boolean(document.querySelector("#save")?.disabled),
    diagnostics: document.querySelector("#diagnostics")?.textContent || "",
  }));
}

async function waitForAudit(page, predicate, label, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  let current = null;
  while (Date.now() < deadline) {
    current = await audit(page);
    if (predicate(current)) return current;
    await page.waitForTimeout(80);
  }
  throw new Error(`${label}: ${JSON.stringify(current)}`);
}

async function saveSource(page, source, expectedStatus = "ready") {
  await page.locator("#editor").fill(source);
  await page.click("#save");
  return waitForAudit(
    page,
    value => value.source === source
      && value.snapshotStatus === expectedStatus
      && value.saveInFlight === false,
    `save did not settle as ${expectedStatus}`,
  );
}

async function refreshUntil(page, predicate, label) {
  const deadline = Date.now() + 20_000;
  let current = null;
  while (Date.now() < deadline) {
    await page.evaluate(() => load(false));
    await page.waitForTimeout(120);
    current = await audit(page);
    if (predicate(current)) return current;
  }
  throw new Error(`${label}: ${JSON.stringify(current)}`);
}

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
  await waitForServer(child);
  const lightweightResponse = await fetch(`${url}/api/status`, { cache: "no-store" });
  assert.equal(lightweightResponse.ok, true);
  const lightweightStatus = await lightweightResponse.json();
  assert.equal(Object.hasOwn(lightweightStatus, "source"), false);
  assert.equal(Object.hasOwn(lightweightStatus, "views"), false);

  const page = await browser.newPage({ viewport: { width: 1280, height: 760 } });
  const browserErrors = [];
  let expectedHttpConsoleErrors = 0;
  page.on("pageerror", error => browserErrors.push(`pageerror: ${error.stack || error.message}`));
  page.on("console", message => {
    if (message.type() !== "error") return;
    const text = message.text();
    if (expectedHttpConsoleErrors > 0 && text.includes("Failed to load resource")) {
      expectedHttpConsoleErrors -= 1;
      return;
    }
    browserErrors.push(`console: ${text}`);
  });

  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => (
    document.querySelector("#status")?.textContent === "ready"
    && window.GlyphSaveTriggeredRendering?.version === 4
    && document.querySelector("#glyph-save-state")
  ), null, { timeout: 10_000 });

  assert.equal(await page.locator("#compile").count(), 0);
  assert.equal((await page.locator("#save").textContent()).trim(), "保存して描画");
  assert.equal(await page.locator("#save").getAttribute("aria-label"), "保存して描画 (Ctrl/Cmd+S)");
  assert.equal(await page.locator("#glyph-save-state").getAttribute("data-persistence"), "saved");
  assert.equal(await page.locator("#glyph-save-state").getAttribute("data-render"), "ready");
  assert.equal(await page.locator("#glyph-save-state").getAttribute("aria-live"), "polite");
  assert.equal(await page.locator("#glyph-stale-banner").getAttribute("role"), "status");

  const beforeTyping = await audit(page);
  const typedSource = `${initialSource}# local-unsaved\n`;
  await page.locator("#editor").fill(typedSource);
  const afterTyping = await waitForAudit(
    page,
    value => value.persistence === "unsaved",
    "typing did not mark the editor unsaved",
  );
  assert.equal(afterTyping.source, beforeTyping.source);
  assert.equal(afterTyping.version, beforeTyping.version);
  const unloadAudit = await page.evaluate(() => {
    const event = new Event("beforeunload", { cancelable: true });
    const dispatched = window.dispatchEvent(event);
    return { dispatched, prevented: event.defaultPrevented };
  });
  assert.equal(unloadAudit.prevented, true);
  assert.equal(unloadAudit.dispatched, false);

  await page.route("**/api/save", async route => {
    await new Promise(resolve => setTimeout(resolve, 350));
    await route.continue();
  });

  const submittedSource = `${initialSource}# submitted\n`;
  const editedDuringSave = `${submittedSource}# edited-during-save\n`;
  await page.locator("#editor").fill(submittedSource);
  await page.click("#save");
  const savingAudit = await waitForAudit(
    page,
    value => value.saveInFlight === true
      && value.renderState === "saving"
      && value.activeSaveRequestId.length > 0,
    "save did not enter the tracked acknowledgement state",
  );
  assert.match(savingAudit.activeSaveRequestId, /^[A-Za-z0-9._-]+$/);
  await page.locator("#editor").fill(editedDuringSave);
  const submittedAudit = await waitForAudit(
    page,
    value => value.source === submittedSource
      && value.saveInFlight === false
      && value.persistence === "unsaved",
    "edit made during save was not preserved",
  );
  assert.equal(submittedAudit.editorSource, editedDuringSave);
  assert.equal(await fs.readFile(sourcePath, "utf8"), submittedSource);

  const queuedFirst = `${editedDuringSave}# queued-first\n`;
  const queuedLatest = `${queuedFirst}# queued-latest\n`;
  await page.locator("#editor").fill(queuedFirst);
  await page.keyboard.press("Control+s");
  const queuedSaving = await waitForAudit(page, value => value.saveInFlight === true, "queued save did not start");
  assert.equal(queuedSaving.saveDisabled, false);
  await page.locator("#editor").fill(queuedLatest);
  await page.click("#save");
  const queuedAudit = await waitForAudit(
    page,
    value => value.source === queuedLatest
      && value.editorSource === queuedLatest
      && value.snapshotStatus === "ready"
      && value.saveInFlight === false
      && value.persistence === "saved",
    "repeated Ctrl+S did not converge on the latest buffer",
  );
  assert(queuedAudit.operationId.length > 0);
  assert.equal(await fs.readFile(sourcePath, "utf8"), queuedLatest);
  await page.unroute("**/api/save");

  const externalClean = `${initialSource}# external-clean\n`;
  await fs.writeFile(sourcePath, externalClean, "utf8");
  const cleanExternalAudit = await refreshUntil(
    page,
    value => value.source === externalClean
      && value.editorSource === externalClean
      && value.snapshotStatus === "ready"
      && value.persistence === "saved",
    "clean editor did not adopt external save",
  );
  assert.equal(cleanExternalAudit.digest, cleanExternalAudit.renderedDigest);

  const localConflict = `${externalClean}# local-conflict\n`;
  const externalConflictA = `${initialSource}# external-conflict-a\n`;
  await page.locator("#editor").fill(localConflict);
  await waitForAudit(page, value => value.persistence === "unsaved", "local conflict source was not dirty");
  await fs.writeFile(sourcePath, externalConflictA, "utf8");
  const conflictA = await refreshUntil(
    page,
    value => value.persistence === "conflict" && value.conflictOpen,
    "dirty editor did not enter external-change conflict",
  );
  assert.equal(conflictA.editorSource, localConflict);
  assert.equal(await fs.readFile(sourcePath, "utf8"), externalConflictA);

  await page.click('#glyph-conflict-dialog [data-action="cancel"]');
  await waitForAudit(page, value => value.persistence === "conflict" && !value.conflictOpen, "cancel did not preserve conflict");
  await page.click("#glyph-save-state");
  await waitForAudit(page, value => value.conflictOpen, "conflict badge did not reopen resolution dialog");

  await page.route("**/api/rebuild", async route => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: "simulated_rebuild_failure", message: "simulated rebuild failure" }),
    });
  });
  expectedHttpConsoleErrors += 1;
  await page.click('#glyph-conflict-dialog [data-action="load"]');
  const failedLoad = await waitForAudit(
    page,
    value => value.persistence === "conflict" && !value.conflictOpen && value.diagnostics.includes("simulated rebuild failure"),
    "failed external load incorrectly resolved conflict",
  );
  assert.equal(failedLoad.editorSource, localConflict);
  await page.unroute("**/api/rebuild");

  await page.click("#glyph-save-state");
  await waitForAudit(page, value => value.conflictOpen, "conflict could not be reopened after load failure");
  const externalConflictB = `${initialSource}# external-conflict-b\n`;
  await fs.writeFile(sourcePath, externalConflictB, "utf8");
  await page.waitForTimeout(60);
  expectedHttpConsoleErrors += 1;
  await page.click('#glyph-conflict-dialog [data-action="overwrite"]');
  const repeatedConflict = await waitForAudit(
    page,
    value => value.persistence === "conflict"
      && value.conflictOpen
      && value.conflict?.source === externalConflictB,
    "overwrite did not reject a newer external change",
  );
  assert.equal(repeatedConflict.editorSource, localConflict);
  assert.equal(await fs.readFile(sourcePath, "utf8"), externalConflictB);

  await page.click('#glyph-conflict-dialog [data-action="overwrite"]');
  const overwritten = await waitForAudit(
    page,
    value => value.source === localConflict
      && value.editorSource === localConflict
      && value.snapshotStatus === "ready"
      && value.persistence === "saved"
      && !value.conflictOpen,
    "explicit overwrite did not converge after refreshed conflict",
  );
  assert.equal(overwritten.digest, overwritten.renderedDigest);
  assert.equal(await fs.readFile(sourcePath, "utf8"), localConflict);

  const brokenSource = "@MAX\n>value():I=MAX\n";
  const brokenAudit = await saveSource(page, brokenSource, "error");
  assert.equal(brokenAudit.persistence, "saved");
  assert.equal(brokenAudit.renderState, "error");
  assert.equal(brokenAudit.staleVisible, true);
  assert.notEqual(brokenAudit.digest, brokenAudit.renderedDigest);
  assert(brokenAudit.staleText.includes("最後に正常コンパイル"), brokenAudit.staleText);

  const recoveredAudit = await saveSource(page, initialSource, "ready");
  assert.equal(recoveredAudit.staleVisible, false);
  assert.equal(recoveredAudit.digest, recoveredAudit.renderedDigest);

  await page.click("#glyph-settings");
  await page.selectOption("#glyph-language", "en");
  assert.equal((await page.locator("#save").textContent()).trim(), "Save & Render");
  assert.equal(await page.locator("#save").getAttribute("aria-label"), "Save & Render (Ctrl/Cmd+S)");
  await page.click("#glyph-settings-close");

  assert.equal(expectedHttpConsoleErrors, 0, "expected HTTP console errors were not observed");
  assert.deepEqual(browserErrors, [], `save-triggered Studio emitted browser errors:\n${browserErrors.join("\n")}`);
  await page.screenshot({
    path: path.join(outputDirectory, "save-triggered-studio.png"),
    fullPage: false,
  });
  await page.close();
} finally {
  await fs.writeFile(sourcePath, initialSource, "utf8");
  await browser.close();
  await stopProcess(child);
}

console.log("verified tracked saves, lightweight polling, queued saves, repeated conflicts, stale diagrams, and unload protection");
