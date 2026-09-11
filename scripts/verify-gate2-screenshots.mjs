import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const screenshotDirectory = resolve("artifacts", "v2", "screenshots");
const manifestPath = resolve(screenshotDirectory, "manifest.json");
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));

const matrixStates = [
  "upload",
  "checking",
  "ready",
  "question-choice",
  "direct-listening",
  "direct-captured",
  "guided-conversation",
  "wording-comparison",
  "exact-review-inline",
  "exact-review-appendix",
  "answer-added",
  "worksheet-review",
  "export-complete",
  "unsupported",
  "voice-unavailable",
];
const tabletStates = new Set([
  "question-choice",
  "guided-conversation",
  "worksheet-review",
]);
const expectedDimensions = {
  desktop: [1440, 1000],
  tablet: [1024, 1366],
  mobile: [390, 844],
};
const expectedFiles = new Map();

for (const state of matrixStates) {
  for (const viewport of ["desktop", "mobile"]) {
    expectedFiles.set(
      `screenshots/${state}-${viewport}.png`,
      expectedDimensions[viewport],
    );
  }
  if (tabletStates.has(state)) {
    expectedFiles.set(
      `screenshots/${state}-tablet.png`,
      expectedDimensions.tablet,
    );
  }
}
for (const viewport of ["desktop", "mobile"]) {
  expectedFiles.set(
    `screenshots/marketing-${viewport}.png`,
    expectedDimensions[viewport],
  );
}
expectedFiles.set(
  "screenshots/worksheet-dialog-mobile.png",
  expectedDimensions.mobile,
);

if (manifest.expectedStateMatrixCaptures !== 33) {
  throw new Error("Gate 2 manifest must declare the 33-image state matrix.");
}
if (manifest.totalCaptures !== expectedFiles.size) {
  throw new Error(
    `Expected ${expectedFiles.size} total captures, found ${manifest.totalCaptures}.`,
  );
}
if (
  !Array.isArray(manifest.externalRequests) ||
  manifest.externalRequests.length
) {
  throw new Error("Visual capture contains an external request.");
}
if (!/^[a-f0-9]{40}$/i.test(manifest.commit)) {
  throw new Error("Visual manifest is not tied to a full commit SHA.");
}

const manifestCaptures = new Map(
  manifest.captures.map((capture) => [capture.file, capture]),
);
for (const [file, [expectedWidth, expectedHeight]] of expectedFiles) {
  const capture = manifestCaptures.get(file);
  if (!capture) throw new Error(`Missing required capture: ${file}`);
  const bytes = await readFile(resolve("artifacts", "v2", file));
  const signature = bytes.subarray(1, 4).toString("ascii");
  if (signature !== "PNG") throw new Error(`${file} is not a PNG.`);
  const actualHash = createHash("sha256").update(bytes).digest("hex");
  if (actualHash !== capture.sha256 || bytes.length !== capture.bytes) {
    throw new Error(`${file} does not match its manifest digest and size.`);
  }
  const width = bytes.readUInt32BE(16);
  const height = bytes.readUInt32BE(20);
  if (width !== expectedWidth || height !== expectedHeight) {
    throw new Error(
      `${file} is ${width}x${height}; expected ${expectedWidth}x${expectedHeight}.`,
    );
  }
}
if (manifestCaptures.size !== expectedFiles.size) {
  throw new Error("Visual manifest includes unexpected captures.");
}

console.log(
  `Verified ${expectedFiles.size} Gate 2 screenshots, dimensions, hashes, and zero external requests.`,
);
