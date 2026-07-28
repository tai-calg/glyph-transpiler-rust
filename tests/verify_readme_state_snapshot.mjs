import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

const generatedPath = path.resolve("build/state-diagram-regression/motor-safety-motor.png");
const committedPath = path.resolve("docs/images/glyph-studio-state-transition.png");
const updateSnapshot = process.env.UPDATE_README_STATE_DIAGRAM === "1";
const sha256 = value => createHash("sha256").update(value).digest("hex");

const generated = await fs.readFile(generatedPath);
if (updateSnapshot) {
  await fs.mkdir(path.dirname(committedPath), { recursive: true });
  await fs.writeFile(committedPath, generated);
  console.log(`updated ${path.relative(process.cwd(), committedPath)}`);
  process.exit(0);
}

const committed = await fs.readFile(committedPath);
const generatedDigest = sha256(generated);
const committedDigest = sha256(committed);

assert.equal(
  committedDigest,
  generatedDigest,
  [
    "README state-transition PNG is stale or was generated from different semantics.",
    `committed sha256: ${committedDigest}`,
    `generated sha256: ${generatedDigest}`,
    "Regenerate and verify it with:",
    "node tests/verify_state_diagram_rendering.mjs && \\",
    "UPDATE_README_STATE_DIAGRAM=1 node tests/verify_readme_state_snapshot.mjs",
    "Commit docs/images/glyph-studio-state-transition.png together with the semantic change.",
  ].join("\n"),
);

console.log(`verified README state-transition snapshot ${generatedDigest}`);
