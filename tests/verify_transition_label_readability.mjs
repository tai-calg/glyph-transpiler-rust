import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const cases = [
  {
    slug: "conveyor",
    file: "examples/state_diagrams/conveyor_control.glyph",
    requiredLabel: "ConveyorStop ➞ set_conveyor(0.0)",
  },
  {
    slug: "traffic-light",
    file: "examples/state_diagrams/traffic_light.glyph",
  },
  {
    slug: "session-protocol",
    file: "examples/state_diagrams/session_protocol.glyph",
  },
];

const outputDirectory = path.resolve("build/transition-label-readability");
await fs.mkdir(outputDirectory, { recursive: true });

const clean = value => String(value ?? "").trim();

function actionLabel(transition) {
  const action = transition?.action;
  return typeof action === "string"
    ? clean(action)
    : clean(action?.display) || clean(action?.expression);
}

function enablingCaseLabel(item, action) {
  const input = item?.input_pattern;
  const inputLabel = input
    ? `${input.confidence === "fallback" ? "? " : ""}${clean(input.display) || clean(input.expression)}`
    : "";
  const guardLabel = clean(item?.guard?.display)
    || clean(item?.guard?.expression).replace(/^true$/i, "");
  const left = `${inputLabel}${guardLabel ? `${inputLabel ? " " : ""}[${guardLabel}]` : ""}`.trim();
  return `${left}${action ? `${left ? " " : ""}➞ ${action}` : ""}`.trim();
}

function expectedLabel(transition) {
  const action = actionLabel(transition);
  const enablingCases = Array.isArray(transition?.enabling_cases)
    ? transition.enabling_cases
    : [];
  if (enablingCases.length) {
    return enablingCases
      .map(item => enablingCaseLabel(item, action))
      .filter(Boolean)
      .join(" || ");
  }

  const trigger = transition?.trigger;
  let input = "otherwise";
  if (trigger && clean(trigger.display)) {
    input = `${trigger.role === "provisional-trigger" ? "? " : ""}${clean(trigger.display)}`;
  } else if (clean(transition?.event)) {
    input = clean(transition.event);
  } else if (Array.isArray(transition?.unclassified_conditions) && transition.unclassified_conditions.length) {
    input = `? ${transition.unclassified_conditions.map(clean).filter(Boolean).join(" & ")}`;
  }
  const guards = Array.isArray(transition?.guards)
    ? transition.guards.map(clean).filter(Boolean)
    : clean(transition?.guard) ? [clean(transition.guard)] : [];
  return `${input}${guards.length ? ` [${guards.join(" & ")}]` : ""}${action ? ` ➞ ${action}` : ""}`;
}

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

async function inspectLabels(page) {
  return page.evaluate(() => {
    const stage = document.querySelector(".graph-stage");
    const stageRect = stage?.getBoundingClientRect();
    const nodes = [...document.querySelectorAll(".state-node")].map(node => node.getBoundingClientRect());
    const overlaps = (left, right, gap = 1) => !(
      left.right <= right.left + gap || right.right <= left.left + gap
      || left.bottom <= right.top + gap || right.bottom <= left.top + gap
    );
    const labels = [...document.querySelectorAll(".transition-io-cluster")].map(cluster => {
      const value = cluster.querySelector(".transition-io-value");
      const node = cluster.querySelector(".transition-io-node.io");
      const style = getComputedStyle(value);
      const rect = value.getBoundingClientRect();
      const nodeRect = node.getBoundingClientRect();
      return {
        id: cluster.dataset.transitionId,
        text: (value.textContent || "").trim(),
        semanticText: (cluster.dataset.ioValue || "").trim(),
        fontSize: Number.parseFloat(style.fontSize || "0"),
        whiteSpace: style.whiteSpace,
        textOverflow: style.textOverflow,
        overflowX: style.overflowX,
        overflowY: style.overflowY,
        horizontalClipping: value.scrollWidth > value.clientWidth + 1.5,
        verticalClipping: value.scrollHeight > value.clientHeight + 1.5,
        outsideBox: rect.left < nodeRect.left - 1.5 || rect.top < nodeRect.top - 1.5
          || rect.right > nodeRect.right + 1.5 || rect.bottom > nodeRect.bottom + 1.5,
        distance: Number(cluster.dataset.ioDistance || 0),
        rect: cluster.getBoundingClientRect(),
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
    const outside = stageRect ? labels.filter(({ rect }) => (
      rect.left < stageRect.left - 1 || rect.top < stageRect.top - 1
      || rect.right > stageRect.right + 1 || rect.bottom > stageRect.bottom + 1
    )).map(item => item.id) : ["missing-stage"];
    return { labels, collisions, outside };
  });
}

const browser = await chromium.launch({ headless: true });
try {
  let port = 8910;
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

    const url = `http://127.0.0.1:${port}`;
    try {
      const apiState = await waitForServer(url, child, logs);
      const page = await browser.newPage({ viewport: { width: 1800, height: 1100 } });
      await page.goto(url, { waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => document.querySelector("#status")?.textContent === "ready");
      if (!await page.locator('button[data-tab="state"]').evaluate(button => button.classList.contains("active"))) {
        await page.click('button[data-tab="state"]');
      }

      for (const machine of apiState.views.state.machines) {
        if (apiState.views.state.machines.length > 1) {
          await page.selectOption("#machine-select", { label: machine.name });
        }
        await page.waitForFunction(({ machineName, transitionCount }) => {
          const stage = document.querySelector(".state-node")?.closest(".graph-stage");
          return document.querySelector("#machine-select")?.selectedOptions?.[0]?.textContent === machineName
            && stage?.dataset.transitionLayoutState === "ready"
            && stage?.dataset.transitionPublicationReady === "true"
            && stage?.dataset.transitionIoClustersReady === "true"
            && stage?.dataset.transitionLayoutProfile === "ordinary"
            && stage?.dataset.stateDiagramWorkspaceGeometryReady === "true"
            && stage?.dataset.initialRouteReady === "true"
            && stage.querySelectorAll(".transition-io-cluster").length === transitionCount
            && !stage.dataset.transitionLayoutError;
        }, { machineName: machine.name, transitionCount: machine.transitions.length }, { timeout: 10_000 });

        const expected = machine.transitions.map((transition, index) => ({
          id: transition.id || `T${index + 1}`,
          text: expectedLabel(transition),
        }));
        const inspection = await inspectLabels(page);
        assert.deepEqual(
          inspection.labels.map(({ id, text }) => ({ id, text })),
          expected,
          `${testCase.slug}/${machine.name}: visible text differs from semantic label`,
        );
        assert(inspection.labels.every(label => label.text === label.semanticText));
        assert(inspection.labels.every(label => label.fontSize >= 9));
        assert(inspection.labels.every(label => label.whiteSpace !== "nowrap"));
        assert(inspection.labels.every(label => label.textOverflow !== "ellipsis"));
        assert(inspection.labels.every(label => !label.horizontalClipping && !label.verticalClipping && !label.outsideBox));
        assert(inspection.labels.every(label => label.distance <= 96.5));
        assert.deepEqual(inspection.collisions, [], `${testCase.slug}/${machine.name}: label collision`);
        assert.deepEqual(inspection.outside, [], `${testCase.slug}/${machine.name}: label outside diagram`);

        if (testCase.requiredLabel) {
          assert(inspection.labels.some(label => label.text === testCase.requiredLabel), inspection.labels.map(label => label.text).join("\n"));
        }

        const exportedLabels = await page.evaluate(() => {
          const markup = window.svg();
          const documentValue = new DOMParser().parseFromString(markup, "image/svg+xml");
          return [...documentValue.querySelectorAll(".transition-io-export-label")].map(item => item.getAttribute("data-full-label"));
        });
        assert.deepEqual(exportedLabels, expected.map(item => item.text), `${testCase.slug}/${machine.name}: SVG lost full labels`);

        await page.screenshot({
          path: path.join(outputDirectory, `${testCase.slug}-${machine.name.toLowerCase()}.png`),
          fullPage: true,
        });
      }
      await page.close();
    } finally {
      await stopProcess(child);
      port += 1;
    }
  }
} finally {
  await browser.close();
}

console.log("verified transition labels remain complete, readable, collision-free and exportable");
