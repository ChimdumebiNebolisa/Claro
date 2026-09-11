import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "@playwright/test";

const baseUrl = process.env.CLAROS_CAPTURE_URL ?? "http://127.0.0.1:5173";
const outputDirectory = resolve("artifacts", "v2", "screenshots");

const scenarios = [
  ["upload", "/app?fixture=upload", "Bring in a worksheet."],
  ["checking", "/app?fixture=checking", "Checking your worksheet."],
  ["ready", "/app?fixture=ready", "Your worksheet is ready."],
  [
    "question-choice",
    "/app/fixture-biology?fixture=question-choice",
    "Why do plants need sunlight?",
  ],
  [
    "direct-listening",
    "/app/fixture-biology?fixture=direct-listening",
    "Why do plants need sunlight?",
  ],
  [
    "direct-captured",
    "/app/fixture-biology?fixture=direct-captured",
    "Why do plants need sunlight?",
  ],
  [
    "guided-conversation",
    "/app/fixture-biology?fixture=guided-conversation",
    "How does sunlight help a plant make food?",
  ],
  [
    "wording-comparison",
    "/app/fixture-biology?fixture=wording-comparison",
    "Choose the wording you want",
  ],
  [
    "exact-review-inline",
    "/app/fixture-biology?fixture=exact-review-inline",
    "Review your exact answer",
  ],
  [
    "exact-review-appendix",
    "/app/fixture-biology?fixture=exact-review-appendix",
    "Review your exact answer",
  ],
  [
    "answer-added",
    "/app/fixture-biology?fixture=answer-added",
    "Answer added to the worksheet.",
  ],
  [
    "worksheet-review",
    "/app/fixture-biology/review?fixture=worksheet-review",
    "Review answers",
  ],
  [
    "export-complete",
    "/app/fixture-biology/export/export_fixture_01?fixture=export-complete",
    "Your completed PDF is ready",
  ],
  ["unsupported", "/app?fixture=unsupported", "Bring in a worksheet."],
  [
    "voice-unavailable",
    "/app/fixture-biology?fixture=voice-unavailable",
    "Why do plants need sunlight?",
  ],
];

const tabletStates = new Set([
  "question-choice",
  "guided-conversation",
  "worksheet-review",
]);

const viewports = {
  desktop: { width: 1440, height: 1000 },
  tablet: { width: 1024, height: 1366 },
  mobile: { width: 390, height: 844 },
};

await mkdir(outputDirectory, { recursive: true });
const browser = await chromium.launch();
const externalRequests = [];
const files = [];

function isLocalRequest(requestUrl) {
  try {
    const { hostname, protocol } = new URL(requestUrl);
    return (
      ["data:", "blob:"].includes(protocol) ||
      ["127.0.0.1", "localhost", "::1"].includes(hostname)
    );
  } catch {
    return false;
  }
}

async function newTrackedPage(label, viewport) {
  const page = await browser.newPage({ viewport: viewports[viewport] });
  page.on("request", (request) => {
    if (!isLocalRequest(request.url())) {
      externalRequests.push({ capture: label, url: request.url() });
    }
  });
  return page;
}

async function capture(name, route, heading, viewport) {
  const page = await newTrackedPage(`${name}-${viewport}`, viewport);
  await page.goto(`${baseUrl}${route}`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: heading, exact: true }).waitFor();
  await page.evaluate(() => document.fonts.ready);
  if (viewport === "desktop" && route.startsWith("/app/")) {
    await page
      .getByRole("img", { name: /showing question \d+ and its answer area/i })
      .waitFor({ timeout: 60_000 });
  }
  const path = resolve(outputDirectory, `${name}-${viewport}.png`);
  await page.screenshot({ path, animations: "disabled" });
  files.push(path);
  await page.close();
}

for (const [name, route, heading] of scenarios) {
  await capture(name, route, heading, "desktop");
  await capture(name, route, heading, "mobile");
  if (tabletStates.has(name)) {
    await capture(name, route, heading, "tablet");
  }
}

await capture(
  "marketing",
  "/",
  "The answer is yours. Getting it onto the page can be easier.",
  "desktop",
);
await capture(
  "marketing",
  "/",
  "The answer is yours. Getting it onto the page can be easier.",
  "mobile",
);

{
  const page = await newTrackedPage("worksheet-dialog-mobile", "mobile");
  await page.goto(`${baseUrl}/app/fixture-biology?fixture=question-choice`, {
    waitUntil: "networkidle",
  });
  await page
    .locator(".v2-mobile-document-action")
    .getByRole("button", { name: "View worksheet" })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("status")
    .filter({ hasText: "Original worksheet ready. Read only." })
    .waitFor({ timeout: 60_000 });
  const viewer = page.getByRole("dialog").locator("embedpdf-container");
  await page.waitForFunction(
    (container) => {
      const images = container?.shadowRoot
        ? [...container.shadowRoot.querySelectorAll("img")]
        : [];
      return images.some(
        (image) =>
          image.complete &&
          image.naturalWidth > 0 &&
          image.getBoundingClientRect().height > 100,
      );
    },
    await viewer.elementHandle(),
    { timeout: 60_000 },
  );
  const path = resolve(outputDirectory, "worksheet-dialog-mobile.png");
  await page.screenshot({ path, animations: "disabled" });
  files.push(path);
  await page.close();
}

await browser.close();

if (externalRequests.length > 0) {
  throw new Error(
    `Capture made external requests:\n${externalRequests
      .map(({ capture, url }) => `${capture}: ${url}`)
      .join("\n")}`,
  );
}

const evidence = [];
for (const path of files) {
  const bytes = await readFile(path);
  evidence.push({
    file: path
      .replace(`${resolve("artifacts", "v2")}\\`, "")
      .replaceAll("\\", "/"),
    sha256: createHash("sha256").update(bytes).digest("hex"),
    bytes: bytes.length,
  });
}

const commit = execFileSync("git", ["rev-parse", "HEAD"], {
  encoding: "utf8",
}).trim();
await writeFile(
  resolve(outputDirectory, "manifest.json"),
  `${JSON.stringify(
    {
      commit,
      baseUrl,
      expectedStateMatrixCaptures: 33,
      totalCaptures: evidence.length,
      externalRequests: [],
      captures: evidence,
    },
    null,
    2,
  )}\n`,
  "utf8",
);

console.log(
  `Captured ${files.length} Gate 2 browser images with no external requests.`,
);
