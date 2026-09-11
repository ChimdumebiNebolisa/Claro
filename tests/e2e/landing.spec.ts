import AxeBuilder from "@axe-core/playwright";
import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";

const forbiddenMarketingBundles = /(?:embedpdf|pdfium|realtime)/i;

test("V2 marketing loads no PDF or Realtime stack", async ({
  page,
}, testInfo) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));

  await page.goto("/");

  await expect(
    page.getByRole("heading", {
      name: "The answer is yours. Getting it onto the page can be easier.",
    }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: /Try Claros/ })).toHaveCount(3);
  await expect(
    page.getByRole("link", { name: /Try Claros/ }).first(),
  ).toBeVisible();
  await expect(page.locator("canvas, iframe")).toHaveCount(0);
  expect(requests.filter((url) => forbiddenMarketingBundles.test(url))).toEqual(
    [],
  );

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);

  const screenshot = testInfo.outputPath("gate1-marketing-shell.png");
  await page.screenshot({ path: screenshot, fullPage: true });
  await testInfo.attach("gate1-marketing-shell", {
    path: screenshot,
    contentType: "image/png",
  });
});

test("V2 workspace is task-first and keeps Realtime lazy", async ({
  page,
}, testInfo) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));

  await page.goto("/app/assignment_123");

  await expect(
    page.getByRole("heading", { name: "Why do plants need sunlight?" }),
  ).toBeVisible();
  await expect(page.getByLabel("Worksheet source context")).toBeVisible();
  await expect(
    page.getByRole("img", {
      name: /original worksheet excerpt/i,
    }),
  ).toBeVisible({ timeout: 60_000 });
  const taskPrecedesSource = await page.evaluate(() => {
    const task = document.querySelector(".v2-task");
    const source = document.querySelector(".v2-source-pane");
    return Boolean(
      task &&
      source &&
      task.compareDocumentPosition(source) & Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });
  expect(taskPrecedesSource).toBe(true);
  expect(requests.filter((url) => /realtime-adapter/i.test(url))).toEqual([]);

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);

  const screenshot = testInfo.outputPath("gate1-workspace-shell.png");
  await page.screenshot({ path: screenshot, fullPage: true });
  await testInfo.attach("gate1-workspace-shell", {
    path: screenshot,
    contentType: "image/png",
  });
});

test("upload picker is keyboard operable with a 44px target", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.goto("/app");
  const choosePdf = page.getByRole("button", {
    name: "Choose a PDF",
    exact: true,
  });
  await expect(choosePdf).toBeVisible();

  const bounds = await choosePdf.boundingBox();
  expect(bounds?.width).toBeGreaterThanOrEqual(44);
  expect(bounds?.height).toBeGreaterThanOrEqual(44);

  await choosePdf.focus();
  const chooserPromise = page.waitForEvent("filechooser");
  await choosePdf.press("Enter");
  await chooserPromise;
  expect(
    requests.filter((url) => /(?:embedpdf|pdfium|biology\/source)/i.test(url)),
  ).toEqual([]);
});

test("mobile worksheet dialog restores focus and has no overflow", async ({
  page,
}, testInfo) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/assignment_123");

  const viewWorksheet = page
    .locator(".v2-mobile-document-action")
    .getByRole("button", { name: "View worksheet" });
  await expect(viewWorksheet).toBeVisible();
  await viewWorksheet.focus();
  await viewWorksheet.press("Enter");

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("status")).toContainText(
    "Original worksheet ready. Read only.",
    { timeout: 60_000 },
  );
  await expect(dialog.getByRole("button", { name: /comment/i })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: /protect/i })).toHaveCount(0);
  const closeWorksheet = dialog.getByRole("button", {
    name: "Close worksheet",
  });
  const closeBounds = await closeWorksheet.boundingBox();
  expect(closeBounds?.width).toBeGreaterThanOrEqual(44);
  expect(closeBounds?.height).toBeGreaterThanOrEqual(44);
  expect(
    requests.filter((url) => {
      if (!url.startsWith("http")) return false;
      return new URL(url).hostname !== "127.0.0.1";
    }),
  ).toEqual([]);
  const dialogScreenshot = testInfo.outputPath("gate1-worksheet-dialog.png");
  await page.screenshot({ path: dialogScreenshot, fullPage: true });
  await testInfo.attach("gate1-worksheet-dialog", {
    path: dialogScreenshot,
    contentType: "image/png",
  });
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(viewWorksheet).toBeFocused();

  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);

  const screenshot = testInfo.outputPath("gate1-workspace-mobile.png");
  await page.screenshot({ path: screenshot, fullPage: true });
  await testInfo.attach("gate1-workspace-mobile", {
    path: screenshot,
    contentType: "image/png",
  });
});

test("legacy V1 remains isolated during migration", async ({ page }) => {
  await page.goto("/legacy");

  await expect(
    page.getByRole("heading", {
      name: /The answer is yours\.\s*Getting it onto the page can be easier\./,
    }),
  ).toBeVisible();
  await expect(page.locator(".legacy-root")).toBeVisible();

  await page.evaluate(() => {
    window.history.pushState({}, "", "/app");
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  const choosePdf = page.getByRole("button", {
    name: "Choose a PDF",
    exact: true,
  });
  await expect(choosePdf).toBeVisible();
  await expect(page.locator(".legacy-root")).toHaveCount(0);
  await choosePdf.focus();
  const postLegacyStyles = await choosePdf.evaluate((element) => {
    const styles = getComputedStyle(element);
    return {
      height: element.getBoundingClientRect().height,
      outlineStyle: styles.outlineStyle,
      outlineWidth: styles.outlineWidth,
    };
  });
  expect(postLegacyStyles.height).toBeGreaterThanOrEqual(44);
  expect(postLegacyStyles.outlineStyle).not.toBe("none");
  expect(postLegacyStyles.outlineWidth).not.toBe("0px");
});

test("health and unknown API routes remain server-addressable", async ({
  request,
}) => {
  const health = await request.get("http://127.0.0.1:8787/health");
  expect(health.ok()).toBe(true);
  expect(await health.json()).toEqual({ status: "ok" });

  const unknownApi = await request.get(
    "http://127.0.0.1:8787/api/v2/not-a-route",
  );
  expect(unknownApi.status()).toBe(404);

  const spa = await request.get(
    "http://127.0.0.1:8787/app/assignment_123/review",
  );
  expect(spa.ok()).toBe(true);
  expect(spa.headers()["content-type"]).toContain("text/html");

  const sourceRange = await request.get(
    "http://127.0.0.1:8787/api/v2/fixtures/biology/source",
    { headers: { Range: "bytes=0-31" } },
  );
  expect(sourceRange.status()).toBe(206);
  expect(sourceRange.headers()["accept-ranges"]).toBe("bytes");
  expect(sourceRange.headers()["content-range"]).toMatch(/^bytes 0-31\//);

  const questionTwoContext = await request.get(
    "http://127.0.0.1:8787/api/v2/fixtures/biology/page-context?question_id=q_02",
  );
  expect(questionTwoContext.ok()).toBe(true);
  const questionTwoMetadata = await questionTwoContext.json();
  expect(questionTwoMetadata).toMatchObject({
    assignment_id: "fixture-biology",
    question_id: "q_02",
    question_index: 2,
    page_number: 1,
    source_status: "original_page_unchanged",
    source_url: "/api/v2/fixtures/biology/source",
  });

  const source = await request.get(
    "http://127.0.0.1:8787/api/v2/fixtures/biology/source",
  );
  expect(source.ok()).toBe(true);
  expect(
    createHash("sha256")
      .update(await source.body())
      .digest("hex"),
  ).toBe(questionTwoMetadata.source_sha256);

  const confirmedPreviewContext = await request.get(
    "http://127.0.0.1:8787/api/v2/fixtures/biology/page-context?question_id=q_02&preview=confirmed",
  );
  expect(confirmedPreviewContext.ok()).toBe(true);
  const confirmedPreviewMetadata = await confirmedPreviewContext.json();
  expect(confirmedPreviewMetadata).toMatchObject({
    assignment_id: "fixture-biology",
    question_id: "q_02",
    question_index: 2,
    page_number: 1,
    source_status: "completed_copy_preview",
    source_url: "/api/v2/fixtures/biology/export",
  });
  expect(confirmedPreviewMetadata.source_sha256).not.toBe(
    questionTwoMetadata.source_sha256,
  );

  const completedPreview = await request.get(
    "http://127.0.0.1:8787/api/v2/fixtures/biology/export",
  );
  expect(completedPreview.ok()).toBe(true);
  expect(
    createHash("sha256")
      .update(await completedPreview.body())
      .digest("hex"),
  ).toBe(confirmedPreviewMetadata.source_sha256);

  const csp = spa.headers()["content-security-policy"];
  expect(csp).toContain("worker-src 'self' blob:");
  expect(csp).toContain("'wasm-unsafe-eval'");
});

test("built app renders the authorized crop and viewer under production CSP", async ({
  page,
}, testInfo) => {
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.route("**/api/v2/assignments/assignment_123", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        assignment_id: "assignment_123",
        version: 2,
        status: "ready",
        title: "Photosynthesis and plant cells",
        source: {
          filename: "biology-short-answer.pdf",
          size_bytes: 4_096,
          sha256:
            "ccba948e849e849b80f4ce8f9d218e726b93a2efbb9eb730aabd5187e743b8d6",
          page_count: 1,
        },
        question_count: 1,
        placement_summary: { inline_possible: 1, appendix_only: 0 },
        warnings: [],
        questions: [
          {
            question_id: "q_01",
            index: 1,
            prompt: "Why do plants need sunlight?",
            instruction:
              "Use evidence from the lesson in one or two sentences.",
            page_number: 1,
            placement_capability: "inline_possible",
            candidate: null,
            wording_comparison: null,
            confirmed_answer: null,
          },
        ],
      }),
    });
  });
  await page.route(
    "**/api/v2/assignments/assignment_123/pages/1/context?**",
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({
          version: 2,
          question_id: "q_01",
          question_index: 1,
          page_number: 1,
          source_sha256:
            "ccba948e849e849b80f4ce8f9d218e726b93a2efbb9eb730aabd5187e743b8d6",
          source_url: "/api/v2/fixtures/biology/source",
          source_status: "original",
          crop: {
            x_mpt: 36_000,
            y_mpt: 195_000,
            width_mpt: 540_000,
            height_mpt: 180_000,
          },
        }),
      });
    },
  );
  await page.route(
    "**/api/v2/assignments/assignment_123/source",
    async (route) => {
      const response = await route.fetch({
        url: "http://127.0.0.1:8787/api/v2/fixtures/biology/source",
      });
      await route.fulfill({ response });
    },
  );

  const response = await page.goto("http://127.0.0.1:8787/app/assignment_123");
  expect(response?.headers()["content-security-policy"]).toContain(
    "script-src 'self' 'wasm-unsafe-eval'",
  );
  await expect(
    page.getByRole("img", {
      name: /original worksheet excerpt/i,
    }),
  ).toBeVisible({ timeout: 60_000 });

  await page
    .locator(".v2-source-heading")
    .getByRole("button", { name: "View worksheet" })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("status")).toContainText(
    "Original worksheet ready. Read only.",
    { timeout: 60_000 },
  );
  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);

  const screenshot = testInfo.outputPath("gate1-production-document.png");
  await page.screenshot({ path: screenshot, fullPage: true });
  await testInfo.attach("gate1-production-document", {
    path: screenshot,
    contentType: "image/png",
  });
});
