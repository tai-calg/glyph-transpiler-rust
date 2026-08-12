import assert from "node:assert/strict";
import { Key } from "webdriverio";

const POINTER_ACTION_BUDGET_MS = 5_000;

async function waitForInnerStudio() {
  const frame = await $("#studio-frame");
  await frame.waitForDisplayed({ timeout: 45_000 });
  await browser.switchFrame(frame);

  await browser.waitUntil(
    async () => browser.execute(() => document.querySelector("#status")?.textContent === "ready"),
    {
      timeout: 45_000,
      timeoutMsg: "Glyph sidecar did not publish a ready Studio inside the Tauri iframe",
    },
  );
}

async function waitForExactCompletionIndex() {
  await browser.waitUntil(
    async () => browser.execute(() => {
      const runtime = window.GlyphEditorDocument;
      const snapshot = window.GlyphEditorLexicalIndex?.snapshot?.();
      return Boolean(
        runtime
        && snapshot
        && Number(snapshot.revision) === Number(runtime.revision?.()),
      );
    }),
    {
      timeout: 15_000,
      timeoutMsg: "editor lexical index did not converge to the active revision",
    },
  );
}

async function waitForStateDiagramReady() {
  await browser.waitUntil(
    async () => browser.execute(() => {
      const stage = document.querySelector(".state-node")?.closest(".graph-stage");
      const transaction = window.glyphTransitionLayoutTransaction;
      return Boolean(
        stage
        && stage.dataset.transitionLayoutState === "ready"
        && stage.dataset.transitionPublicationReady === "true"
        && transaction
        && transaction.generation === transaction.completedGeneration,
      );
    }),
    {
      timeout: 30_000,
      timeoutMsg: "state diagram did not reach a published ready layout",
    },
  );
}

describe("Glyph Studio macOS native Desktop E2E", () => {
  it("accepts completion by Tab and completes a real W3C pointer drag without native WebKit blocking", async () => {
    await waitForInnerStudio();

    // 目的: 前回到達していたキーボードcompletion acceptanceをTauri実アプリで保持する。
    // 手段: 保存は行わずeditor bufferだけに型名補完コンテキストを追加し、Tabで受理する。
    await browser.waitUntil(
      async () => browser.execute(() => Boolean(
        window.GlyphEditorCompletion?.version >= 2
        && window.GlyphEditorLexicalIndex?.version >= 2
        && window.GlyphEditorDocument?.version >= 1
      )),
      { timeout: 15_000, timeoutMsg: "completion runtime was not initialized" },
    );
    await waitForExactCompletionIndex();

    const originalSource = await browser.execute(() => document.getElementById("editor")?.value || "");
    assert(originalSource.includes("DoorState"), "default desktop fixture must contain DoorState");

    await browser.execute((source) => {
      const editor = document.getElementById("editor");
      editor.value = `${source}\n*Probe(value:Do`;
      editor.focus();
      editor.setSelectionRange(editor.value.length, editor.value.length);
      editor.dispatchEvent(new InputEvent("input", {
        bubbles: true,
        inputType: "insertText",
        data: "o",
      }));
    }, originalSource);
    await waitForExactCompletionIndex();

    await browser.waitUntil(
      async () => browser.execute(() => {
        const popup = document.getElementById("glyph-completion-popup");
        return Boolean(
          popup
          && !popup.hidden
          && window.GlyphEditorCompletion?.candidates?.().some(item => item.text === "DoorState"),
        );
      }),
      { timeout: 10_000, timeoutMsg: "DoorState completion candidate did not appear" },
    );

    await browser.keys([Key.Tab]);
    await browser.waitUntil(
      async () => browser.execute(() => document.getElementById("editor")?.value.endsWith("DoorState")),
      { timeout: 5_000, timeoutMsg: "Tab did not accept DoorState completion" },
    );

    // 入力したE2E専用bufferを戻し、production diagramの既存compiled snapshotを操作する。
    await browser.execute((source) => {
      const editor = document.getElementById("editor");
      window.GlyphEditorCompletion?.close?.();
      editor.value = source;
      editor.setSelectionRange(editor.value.length, editor.value.length);
      editor.dispatchEvent(new InputEvent("input", {
        bubbles: true,
        inputType: "historyUndo",
        data: null,
      }));
    }, originalSource);
    await waitForExactCompletionIndex();

    const stateTab = await $('button[data-tab="state"]');
    await stateTab.waitForExist({ timeout: 10_000 });
    await stateTab.click();
    await waitForStateDiagramReady();

    const node = await $(".state-node.initial-target");
    await node.waitForDisplayed({ timeout: 10_000 });

    const before = await browser.execute(() => {
      const target = document.querySelector(".state-node.initial-target");
      const path = document.querySelector("path.initial-transition-path");
      return {
        left: Number.parseFloat(target?.style.left || "0") || 0,
        top: Number.parseFloat(target?.style.top || "0") || 0,
        path: path?.getAttribute("d") || "",
      };
    });
    assert(before.path, "initial transition path is missing before pointer drag");

    // 目的: native WebKit driverで約20秒停止していたW3C pointer actionを回帰検証する。
    // 手段: embedded WebDriverへ同じpointerMove/down/move/up系列を送信する。
    const startedAt = Date.now();
    await browser
      .action("pointer", { parameters: { pointerType: "mouse" } })
      .move({ duration: 0, origin: node, x: 0, y: 0 })
      .down({ button: 0 })
      .pause(20)
      .move({ duration: 120, origin: "pointer", x: 120, y: 90 })
      .up({ button: 0 })
      .perform();
    const pointerActionMs = Date.now() - startedAt;

    assert(
      pointerActionMs < POINTER_ACTION_BUDGET_MS,
      `W3C pointer action exceeded ${POINTER_ACTION_BUDGET_MS} ms: ${pointerActionMs} ms`,
    );

    await browser.waitUntil(
      async () => browser.execute((previous) => {
        const target = document.querySelector(".state-node.initial-target");
        const path = document.querySelector("path.initial-transition-path");
        const left = Number.parseFloat(target?.style.left || "0") || 0;
        const top = Number.parseFloat(target?.style.top || "0") || 0;
        return (
          (Math.abs(left - previous.left) > 1 || Math.abs(top - previous.top) > 1)
          && Boolean(path?.getAttribute("d"))
          && path.getAttribute("d") !== previous.path
        );
      }, before),
      { timeout: 10_000, timeoutMsg: "pointer action returned but the production node did not move" },
    );

    await waitForStateDiagramReady();

    const after = await browser.execute(() => {
      const target = document.querySelector(".state-node.initial-target");
      const stage = target?.closest(".graph-stage");
      const digest = window.snapshot?.digest || "source";
      const machine = document.getElementById("machine-select")?.value || 0;
      const storageKey = `glyph.diagram.positions.v1:${digest}:state:${machine}`;
      return {
        left: Number.parseFloat(target?.style.left || "0") || 0,
        top: Number.parseFloat(target?.style.top || "0") || 0,
        layoutState: stage?.dataset.transitionLayoutState || "",
        publicationReady: stage?.dataset.transitionPublicationReady || "",
        persisted: Boolean(localStorage.getItem(storageKey)),
        bodyConnected: document.body?.isConnected === true,
      };
    });

    assert.notDeepEqual(
      { left: after.left, top: after.top },
      { left: before.left, top: before.top },
      "initial state node position was unchanged",
    );
    assert.equal(after.layoutState, "ready");
    assert.equal(after.publicationReady, "true");
    assert.equal(after.persisted, true, "dragged node position was not persisted");
    assert.equal(after.bodyConnected, true, "Tauri Studio document became detached after drag");

    console.log(JSON.stringify({ pointerActionMs, before, after }));
  });
});
