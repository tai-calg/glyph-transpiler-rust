import { invoke } from "@tauri-apps/api/core";

const frame = document.getElementById("studio-frame");
const loading = document.getElementById("loading");
const status = document.getElementById("status");
const sourceLabel = document.getElementById("source-label");
const openButton = document.getElementById("open-file");
const restartButton = document.getElementById("restart");

let currentSource = null;
let generation = 0;

function setBusy(message) {
  loading.hidden = false;
  frame.hidden = true;
  status.textContent = message;
  openButton.disabled = true;
  restartButton.disabled = true;
}

function showStudio(info) {
  currentSource = info.source;
  sourceLabel.textContent = info.source;
  const expectedGeneration = ++generation;
  frame.onload = () => {
    if (expectedGeneration !== generation) return;
    loading.hidden = true;
    frame.hidden = false;
    openButton.disabled = false;
    restartButton.disabled = false;
  };
  frame.src = info.url;
}

function showError(error) {
  loading.hidden = false;
  frame.hidden = true;
  status.textContent = String(error);
  openButton.disabled = false;
  restartButton.disabled = currentSource === null;
}

async function start() {
  setBusy("Starting the local Glyph compiler…");
  try {
    showStudio(await invoke("initialize_backend"));
  } catch (error) {
    showError(error);
  }
}

openButton.addEventListener("click", async () => {
  setBusy("Opening Glyph source…");
  try {
    const info = await invoke("open_glyph_file");
    if (info) showStudio(info);
    else if (currentSource) {
      loading.hidden = true;
      frame.hidden = false;
      openButton.disabled = false;
      restartButton.disabled = false;
    } else {
      showError("No Glyph file selected.");
    }
  } catch (error) {
    showError(error);
  }
});

restartButton.addEventListener("click", async () => {
  setBusy("Restarting the local Glyph compiler…");
  try {
    showStudio(await invoke("restart_backend"));
  } catch (error) {
    showError(error);
  }
});

window.addEventListener("DOMContentLoaded", start, { once: true });
