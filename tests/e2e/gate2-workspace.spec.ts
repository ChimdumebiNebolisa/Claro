import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";

const assignmentPath = "/app/fixture-biology";
const expectedSuggestion =
  "Plants use sunlight to make food through photosynthesis.";
const questionThree = "How can photosynthesis support other living things?";
const directVoiceAnswer =
  "Plants need sunlight because it helps them make their food.";
const appendixVoiceAnswer =
  "Photosynthesis supports other living things by making oxygen and by helping plants grow into food for animals.";

async function expectFocusedHeading(page: Page, name: string | RegExp) {
  const heading = page.getByRole("heading", { level: 1, name });
  await expect(heading).toBeVisible({ timeout: 60_000 });
  await expect(heading).toBeFocused({ timeout: 60_000 });
  return heading;
}

async function expectNoHorizontalOverflow(page: Page) {
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          document.documentElement.scrollWidth -
          document.documentElement.clientWidth,
      ),
    )
    .toBeLessThanOrEqual(0);
}

async function tabTo(page: Page, target: ReturnType<Page["locator"]>) {
  await expect(target).toBeVisible();
  for (let index = 0; index < 40; index += 1) {
    if (await target.evaluate((element) => element === document.activeElement))
      return;
    await page.keyboard.press("Tab");
  }
  await expect(target).toBeFocused();
}

async function expectTaskBeforeSource(page: Page) {
  await expect(page.locator(".v2-task")).toBeAttached({ timeout: 60_000 });
  await expect(page.locator(".v2-source-pane")).toBeAttached({
    timeout: 60_000,
  });
  expect(
    await page.evaluate(() => {
      const task = document.querySelector(".v2-task");
      const source = document.querySelector(".v2-source-pane");
      return Boolean(
        task &&
        source &&
        task.compareDocumentPosition(source) & Node.DOCUMENT_POSITION_FOLLOWING,
      );
    }),
  ).toBe(true);
}

test("active Question 2 and Question 3 crops expose faithful accessible names", async ({
  page,
}) => {
  await page.goto(`${assignmentPath}?fixture=guided-conversation`);
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "How does sunlight help a plant make food?",
    }),
  ).toBeVisible({ timeout: 60_000 });
  await expect(
    page.getByRole("img", {
      name: "Original worksheet excerpt showing question 2 and its answer area",
    }),
  ).toBeVisible({ timeout: 60_000 });

  await page.goto(`${assignmentPath}?fixture=exact-review-appendix`);
  await expectFocusedHeading(page, "Review your exact answer");
  await expect(
    page.getByRole("img", {
      name: "Original worksheet excerpt showing question 3 and its answer area",
    }),
  ).toBeVisible({ timeout: 60_000 });
});

test("direct typed answer requires exact review and supports partial PDF export", async ({
  page,
}, testInfo) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  const exactAnswer =
    "Plants need sunlight because chlorophyll captures energy — it is “stored” as glucose.";

  await page.goto(assignmentPath);
  await expectFocusedHeading(page, "Why do plants need sunlight?");

  await page.getByRole("button", { name: "Type instead" }).click();
  const answer = page.getByRole("textbox", { name: "Your words" });
  await expect(answer).toBeFocused();
  await answer.fill(exactAnswer);
  await expect(answer).toHaveValue(exactAnswer);
  expect(requests.filter((url) => /realtime-adapter/i.test(url))).toEqual([]);

  await page.getByRole("button", { name: "Review answer" }).click();
  await expectFocusedHeading(page, "Review your exact answer");
  await expect(page.getByText(exactAnswer, { exact: true })).toBeVisible();
  await expect(
    page.getByText("Your answer fits on the original worksheet."),
  ).toBeVisible();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);

  await page.getByRole("button", { name: "Use this exact answer" }).click();
  await expectFocusedHeading(page, "Answer added to the worksheet.");
  await expect(page.getByText(exactAnswer, { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Review answers" }).click();
  await expect(page).toHaveURL(`${assignmentPath}/review`);
  await expectFocusedHeading(page, "Review answers");
  await expect(page.locator(".v2-task").getByRole("status")).toContainText(
    "1 of 3 answered. Unanswered questions will stay blank.",
  );
  await expect(page.getByText(exactAnswer, { exact: true })).toBeVisible();
  await expect(page.getByText("Unanswered", { exact: true })).toHaveCount(2);

  await page.getByRole("button", { name: "Download completed PDF" }).click();
  await expectFocusedHeading(page, "Preparing your completed PDF");
  await expect(page).toHaveURL(`${assignmentPath}/export/export_fixture_01`);
  await expectFocusedHeading(page, "Your completed PDF is ready");
  await expect(
    page.getByText(
      "Your original worksheet is unchanged. This download is a new completed copy.",
    ),
  ).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download completed PDF" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(
    "biology-short-answer-completed.pdf",
  );
  const downloadPath = testInfo.outputPath(download.suggestedFilename());
  await download.saveAs(downloadPath);
  const bytes = await readFile(downloadPath);
  expect(bytes.subarray(0, 5).toString("ascii")).toBe("%PDF-");
  expect(bytes.length).toBeGreaterThan(1_000);
  expect(requests.filter((url) => /realtime-adapter/i.test(url))).toEqual([]);
});

test("guided typed flow keeps the student's final wording separate from an approved suggestion", async ({
  page,
}) => {
  const studentTurn = "Sunlight gives the plant energy to make food.";
  const studentFinal =
    "A plant uses sunlight’s energy to turn water and carbon dioxide into food.";

  await page.goto(assignmentPath);
  await page
    .getByRole("button", { name: "Start a guided conversation" })
    .click();
  await expectFocusedHeading(page, "Why do plants need sunlight?");
  await expect(page.getByLabel("Guided conversation")).toContainText(
    "What do you already know about this question?",
  );

  const response = page.getByRole("textbox", { name: "Your response" });
  await response.fill(studentTurn);
  await page.getByRole("button", { name: "Send response" }).click();
  await expect(page.getByLabel("Guided conversation")).toContainText(
    studentTurn,
  );
  await expect(page.getByLabel("Guided conversation")).toContainText(
    "What does sunlight provide that helps the plant make food?",
  );

  await page.getByRole("button", { name: "I am ready to answer" }).click();
  const finalAnswer = page.getByRole("textbox", { name: "Your final answer" });
  await expect(finalAnswer).toHaveValue("");
  await expect(finalAnswer).toBeFocused();
  await finalAnswer.fill(studentFinal);
  await page.getByRole("button", { name: "Make it clearer" }).click();

  await expectFocusedHeading(page, "Choose the wording you want");
  await expect(page.getByText(studentFinal, { exact: true })).toBeVisible();
  await expect(
    page.getByText(expectedSuggestion, { exact: true }),
  ).toBeVisible();

  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);

  await page.getByRole("button", { name: "Use suggestion" }).click();
  await expectFocusedHeading(page, "Review your exact answer");
  await expect(
    page.getByText(expectedSuggestion, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Suggested wording", { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Use this exact answer" }).click();
  await expectFocusedHeading(page, "Answer added to the worksheet.");
  await expect(
    page.getByText(expectedSuggestion, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Suggested wording", { exact: true }),
  ).toBeVisible();
});

test("fake direct voice capture stays editable and enters exact review", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));

  await page.goto(assignmentPath);
  await page.getByRole("button", { name: "Start answering" }).click();
  expect(requests.filter((url) => /realtime-adapter/i.test(url))).toEqual([]);

  await page.getByRole("button", { name: "Start speaking" }).click();
  await expect(
    page.getByLabel("Voice controls").getByRole("status"),
  ).toContainText("Listening");
  await expect(
    page.getByRole("button", { name: "Stop listening" }),
  ).toBeVisible();
  await expect
    .poll(() => requests.filter((url) => /realtime-adapter/i.test(url)).length)
    .toBeGreaterThan(0);

  await page.getByRole("button", { name: "Stop listening" }).click();
  await expect(
    page.getByLabel("Voice controls").getByRole("status"),
  ).toContainText("Captured");
  const captured = page.getByRole("textbox", { name: "Your words" });
  await expect(captured).toHaveValue(
    "Plants need sunlight because it helps them make their food.",
  );
  await captured.fill(
    "Plants need sunlight because it gives them energy to make food.",
  );
  await page.getByRole("button", { name: "Review answer" }).click();
  await expectFocusedHeading(page, "Review your exact answer");
  await expect(
    page.getByText(
      "Plants need sunlight because it gives them energy to make food.",
      { exact: true },
    ),
  ).toBeVisible();
});

test("direct fake voice on Question 3 discloses and confirms attached-page placement", async ({
  page,
}) => {
  await page.goto(`${assignmentPath}/review`);
  const questionRow = page.getByRole("listitem").filter({
    has: page.getByRole("heading", { level: 2, name: questionThree }),
  });
  await questionRow.getByRole("button", { name: "Answer question" }).click();
  await expect(page).toHaveURL(assignmentPath);
  await expectFocusedHeading(page, questionThree);

  await page.getByRole("button", { name: "Start answering" }).click();
  await page.getByRole("button", { name: "Start speaking" }).click();
  await expect(
    page.getByLabel("Voice controls").getByRole("status"),
  ).toContainText("Listening");
  await page.getByRole("button", { name: "Stop listening" }).click();
  await expect(page.getByRole("textbox", { name: "Your words" })).toHaveValue(
    appendixVoiceAnswer,
  );

  await page.getByRole("button", { name: "Review answer" }).click();
  await expectFocusedHeading(page, "Review your exact answer");
  await expect(
    page.getByText("This answer will appear on an attached answer page.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page
      .getByLabel("Review your exact answer")
      .getByText(appendixVoiceAnswer, { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Use this exact answer" }).click();
  await expectFocusedHeading(page, "Answer added to the attached answer page.");
  await expect(
    page.getByRole("img", {
      name: "Completed PDF preview showing question 3 and its answer area",
    }),
  ).toBeVisible({ timeout: 60_000 });
});

test("guided fake voice exposes live captions and a persistent interrupted state", async ({
  page,
}) => {
  await page.goto(`${assignmentPath}?realtime=normal`);
  await page
    .getByRole("button", { name: "Start a guided conversation" })
    .click();
  await page.getByRole("button", { name: "Start speaking" }).click();
  await expect(
    page.getByLabel("Voice controls").getByRole("status"),
  ).toContainText("Listening");
  await page.getByRole("button", { name: "Stop listening" }).click();

  const captions = page.getByLabel("Live captions");
  await expect(captions).toContainText(
    "Sunlight gives the plant energy for the process.",
  );
  await expect(captions).toContainText(
    "Good. State your final answer in your own words.",
  );
  await expect(page.getByLabel("Guided conversation")).toContainText(
    "Sunlight gives the plant energy for the process.",
  );

  await page.getByRole("button", { name: "Interrupt Claros" }).click();
  await expect(
    page.getByLabel("Voice controls").getByRole("status"),
  ).toContainText("Interrupted");
  await expect(
    page.getByText(
      "Claros stopped speaking. Your text and conversation are still available.",
      { exact: true },
    ),
  ).toBeVisible();
});

test("casual voice agreement cannot confirm while the exact phrase confirms only in review", async ({
  page,
}) => {
  const casualAnswer = "Plants use light energy to make food.";
  await page.goto(`${assignmentPath}?realtime=casual`);
  await page.getByRole("button", { name: "Type instead" }).click();
  await page.getByRole("textbox", { name: "Your words" }).fill(casualAnswer);
  await page.getByRole("button", { name: "Review answer" }).click();

  await expect(
    page.getByLabel("Live captions").getByRole("status"),
  ).toContainText("okay");
  await expectFocusedHeading(page, "Review your exact answer");
  await expect(
    page.getByRole("button", { name: "Use this exact answer" }),
  ).toBeVisible();

  const exactPhraseAnswer = "Plants need light to power photosynthesis.";
  await page.goto(`${assignmentPath}?realtime=confirm`);
  await page.getByRole("button", { name: "Type instead" }).click();
  await page
    .getByRole("textbox", { name: "Your words" })
    .fill(exactPhraseAnswer);
  await expect(page.getByRole("heading", { name: /Answer added/ })).toHaveCount(
    0,
  );

  await page.getByRole("button", { name: "Review answer" }).click();
  await expectFocusedHeading(page, "Answer added to the worksheet.");
  await expect(
    page.getByText(exactPhraseAnswer, { exact: true }),
  ).toBeVisible();
});

test("Realtime disconnect preserves a typed draft and completes through typing", async ({
  page,
}) => {
  const draft = "Plants need sunlight because my first thought is";
  const completed =
    "Plants need sunlight because light supplies energy for photosynthesis.";

  await page.goto(`${assignmentPath}?realtime=disconnect`);
  await page.getByRole("button", { name: "Start answering" }).click();
  const answer = page.getByRole("textbox", { name: "Your words" });
  await answer.fill(draft);
  await page.getByRole("button", { name: "Start speaking" }).click();
  await page.getByRole("button", { name: "Stop listening" }).click();

  await expect(
    page.getByLabel("Voice controls").getByRole("status"),
  ).toContainText("Connection lost");
  await expect(answer).toHaveValue(draft);
  await page.getByRole("button", { name: "Continue by typing" }).click();
  await expect(answer).toBeFocused();
  await expect(answer).toHaveValue(draft);

  await answer.fill(completed);
  await page.getByRole("button", { name: "Review answer" }).click();
  await expectFocusedHeading(page, "Review your exact answer");
  await expect(page.getByText(completed, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Use this exact answer" }).click();
  await expectFocusedHeading(page, "Answer added to the worksheet.");
});

test("microphone failure preserves the draft and hands focus to typed completion", async ({
  page,
}) => {
  await page.goto(`${assignmentPath}?fixture=voice-unavailable`);
  await expect(
    page.getByLabel("Voice controls").getByRole("status"),
  ).toContainText("Microphone unavailable", { timeout: 60_000 });
  const answer = page.getByRole("textbox", { name: "Your words" });
  await expect(answer).toHaveValue("Plants need sunlight because");

  await page.getByRole("button", { name: "Continue by typing" }).click();
  await expect(answer).toBeFocused();
  await expect(answer).toHaveValue("Plants need sunlight because");
  await answer.fill(
    "Plants need sunlight because it supplies energy for photosynthesis.",
  );
  await page.getByRole("button", { name: "Review answer" }).click();
  await expectFocusedHeading(page, "Review your exact answer");
  await expect(
    page.getByText(
      "Plants need sunlight because it supplies energy for photosynthesis.",
      { exact: true },
    ),
  ).toBeVisible();
});

test("revision keeps the approved answer until a replacement is freshly confirmed", async ({
  page,
}) => {
  const approved = "Plants use sunlight as energy to make food.";
  const unconfirmedRevision = "This wording has not been approved yet.";
  const confirmedRevision =
    "Plants capture sunlight and use its energy during photosynthesis.";

  await page.goto(assignmentPath);
  await page.getByRole("button", { name: "Type instead" }).click();
  await page.getByRole("textbox", { name: "Your words" }).fill(approved);
  await page.getByRole("button", { name: "Review answer" }).click();
  await page.getByRole("button", { name: "Use this exact answer" }).click();
  await expectFocusedHeading(page, "Answer added to the worksheet.");

  await page.getByRole("button", { name: "Edit answer" }).click();
  const revision = page.getByRole("textbox", { name: "Your words" });
  await expect(revision).toHaveValue(approved);
  await revision.fill(unconfirmedRevision);
  await page.getByRole("link", { name: "Review answers" }).click();
  await expectFocusedHeading(page, "Review answers");
  await expect(page.getByText(approved, { exact: true })).toBeVisible();
  await expect(
    page.getByText(unconfirmedRevision, { exact: true }),
  ).toHaveCount(0);

  await page.getByRole("button", { name: "Edit answer" }).click();
  await expect(revision).toHaveValue(approved);
  await revision.fill(confirmedRevision);
  await page.getByRole("button", { name: "Review answer" }).click();
  await expect(
    page.getByText(confirmedRevision, { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Use this exact answer" }).click();
  await expectFocusedHeading(page, "Answer added to the worksheet.");

  await page.getByRole("link", { name: "Review answers" }).click();
  await expect(
    page.getByText(confirmedRevision, { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(approved, { exact: true })).toHaveCount(0);
});

test("failed export retry preserves the confirmed answer through completion", async ({
  page,
}) => {
  await page.goto(
    `${assignmentPath}/export/export_fixture_01?fixture=export-failed`,
  );
  await expectFocusedHeading(page, "The PDF could not be prepared");
  await expect(
    page.getByText("Your confirmed answers are safe", { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Retry export" }).click();
  await expectFocusedHeading(page, "Preparing your completed PDF");
  await page.evaluate(() => {
    const url = new URL(window.location.href);
    url.searchParams.delete("fixture");
    window.history.replaceState({}, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
  });

  await expectFocusedHeading(page, "Your completed PDF is ready");
  await page.getByRole("button", { name: "Review answers" }).click();
  await expectFocusedHeading(page, "Review answers");
  await expect(
    page.getByText(directVoiceAnswer, { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".v2-task").getByRole("status")).toContainText(
    "1 of 3 answered",
  );
});

test("keyboard-only sample journey reaches and downloads a completed PDF", async ({
  page,
}, testInfo) => {
  const keyboardAnswer =
    "Plants need sunlight because it provides energy for photosynthesis.";
  await page.goto("/app");
  await expectFocusedHeading(page, "Bring in a worksheet.");

  const sample = page.getByRole("button", {
    name: "Try the biology sample",
  });
  await tabTo(page, sample);
  await page.keyboard.press("Enter");
  await expectFocusedHeading(page, "Your worksheet is ready.");

  const startQuestion = page.getByRole("button", { name: "Start Question 1" });
  await tabTo(page, startQuestion);
  await page.keyboard.press("Enter");
  await expectFocusedHeading(page, "Why do plants need sunlight?");

  const typeInstead = page.getByRole("button", { name: "Type instead" });
  await tabTo(page, typeInstead);
  await page.keyboard.press("Enter");
  const answer = page.getByRole("textbox", { name: "Your words" });
  await expect(answer).toBeFocused();
  await page.keyboard.insertText(keyboardAnswer);

  const reviewAnswer = page.getByRole("button", { name: "Review answer" });
  await tabTo(page, reviewAnswer);
  await page.keyboard.press("Enter");
  await expectFocusedHeading(page, "Review your exact answer");

  const confirm = page.getByRole("button", { name: "Use this exact answer" });
  await tabTo(page, confirm);
  await page.keyboard.press("Enter");
  await expectFocusedHeading(page, "Answer added to the worksheet.");

  const reviewWorksheet = page.getByRole("link", { name: "Review answers" });
  await tabTo(page, reviewWorksheet);
  await page.keyboard.press("Enter");
  await expectFocusedHeading(page, "Review answers");

  const createExport = page.getByRole("button", {
    name: "Download completed PDF",
  });
  await tabTo(page, createExport);
  await page.keyboard.press("Enter");
  await expectFocusedHeading(page, "Your completed PDF is ready");

  const downloadLink = page.getByRole("link", {
    name: "Download completed PDF",
  });
  await tabTo(page, downloadLink);
  const downloadPromise = page.waitForEvent("download");
  await page.keyboard.press("Enter");
  const download = await downloadPromise;
  const downloadPath = testInfo.outputPath(download.suggestedFilename());
  await download.saveAs(downloadPath);
  expect((await readFile(downloadPath)).subarray(0, 5).toString("ascii")).toBe(
    "%PDF-",
  );
});

test("task precedes source across desktop, tablet, and mobile layouts", async ({
  page,
}) => {
  const layouts = [
    { name: "desktop", width: 1440, height: 1000 },
    { name: "tablet", width: 1024, height: 1366 },
    { name: "mobile", width: 390, height: 844 },
  ] as const;

  await page.goto(`${assignmentPath}?fixture=question-choice`);
  for (const layout of layouts) {
    await test.step(layout.name, async () => {
      await page.setViewportSize({
        width: layout.width,
        height: layout.height,
      });
      await expectTaskBeforeSource(page);
      await expectNoHorizontalOverflow(page);

      const task = page.locator(".v2-task");
      const source = page.getByLabel("Worksheet source context");
      if (layout.name === "desktop") {
        await expect(source).toBeVisible();
        const taskBox = await task.boundingBox();
        const sourceBox = await source.boundingBox();
        expect(taskBox?.x).toBeLessThan(sourceBox?.x ?? 0);
      } else if (layout.name === "tablet") {
        await expect(source).toBeVisible();
        const taskBox = await task.boundingBox();
        const sourceBox = await source.boundingBox();
        expect(taskBox?.y).toBeLessThan(sourceBox?.y ?? 0);
      } else {
        await expect(source).toBeHidden();
        await expect(
          page
            .locator(".v2-mobile-document-action")
            .getByRole("button", { name: "View worksheet" }),
        ).toBeVisible();
      }
    });
  }
});

test("principal V2 routes have no automated axe violations", async ({
  page,
}) => {
  const routes = [
    { path: "/app?fixture=upload", heading: "Bring in a worksheet." },
    {
      path: `${assignmentPath}?fixture=question-choice`,
      heading: "Why do plants need sunlight?",
    },
    {
      path: `${assignmentPath}/review?fixture=worksheet-review`,
      heading: "Review answers",
    },
    {
      path: `${assignmentPath}/export/export_fixture_01?fixture=export-complete`,
      heading: "Your completed PDF is ready",
    },
  ] as const;

  for (const route of routes) {
    await test.step(route.path, async () => {
      await page.goto(route.path);
      await expect(
        page.getByRole("heading", { level: 1, name: route.heading }),
      ).toBeVisible({ timeout: 60_000 });
      expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    });
  }
});

test("reduced motion and a 200%-zoom-equivalent viewport preserve reflow", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 720, height: 600 });
  await page.goto(`${assignmentPath}?fixture=direct-listening`);

  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(
    page
      .locator(".v2-mobile-document-action")
      .getByRole("button", { name: "View worksheet" }),
  ).toBeVisible();
  await expect(page.getByLabel("Worksheet source context")).toBeHidden();
  await expectNoHorizontalOverflow(page);

  const motionViolations = await page
    .locator(".v2-app-shell *")
    .evaluateAll((elements) => {
      const durationInMilliseconds = (value: string) =>
        value.split(",").map((part) => {
          const duration = part.trim();
          return duration.endsWith("ms")
            ? Number.parseFloat(duration)
            : Number.parseFloat(duration) * 1_000;
        });

      return elements.flatMap((element) => {
        const styles = getComputedStyle(element);
        const animationDurations = durationInMilliseconds(
          styles.animationDuration,
        );
        const transitionDurations = durationInMilliseconds(
          styles.transitionDuration,
        );
        const animationIterations = styles.animationIterationCount
          .split(",")
          .map((value) =>
            value.trim() === "infinite" ? Infinity : Number.parseFloat(value),
          );
        const hasLongAnimation = animationDurations.some(
          (duration) => duration > 0.01,
        );
        const hasLongTransition = transitionDurations.some(
          (duration) => duration > 0.01,
        );
        const repeats = animationIterations.some(
          (iterations) => iterations > 1,
        );
        return hasLongAnimation || hasLongTransition || repeats
          ? [
              {
                tag: element.tagName,
                animationDuration: styles.animationDuration,
                animationIterationCount: styles.animationIterationCount,
                transitionDuration: styles.transitionDuration,
              },
            ]
          : [];
      });
    });
  expect(motionViolations).toEqual([]);
});
