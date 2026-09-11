import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

type StoryIndex = {
  entries: Record<string, { id: string; title: string; type: string }>;
};

test("all V2 stories render without automated accessibility violations", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const response = await page.request.get("/index.json");
  expect(response.ok()).toBe(true);
  const index = (await response.json()) as StoryIndex;
  const stories = Object.values(index.entries)
    .filter((entry) => entry.type === "story" && entry.title.startsWith("V2/"))
    .map((entry) => entry.id)
    .sort();

  expect(stories.length).toBeGreaterThanOrEqual(30);

  for (const storyId of stories) {
    await page.goto(`/iframe.html?id=${storyId}&viewMode=story`, {
      waitUntil: "domcontentloaded",
    });
    const storyRoot = page.locator("#storybook-root");
    await expect(storyRoot).not.toBeEmpty();

    if (storyId.endsWith("authorized-crop")) {
      await expect(
        page.getByRole("img", {
          name: /original worksheet excerpt/i,
        }),
      ).toBeVisible({ timeout: 60_000 });
    }
    if (storyId.endsWith("read-only-worksheet-dialog")) {
      await expect(page.getByRole("status")).toContainText(
        "Original worksheet ready. Read only.",
        { timeout: 60_000 },
      );
    }

    const accessibility = await new AxeBuilder({ page }).analyze();
    expect(
      accessibility.violations,
      `${storyId} has accessibility violations`,
    ).toEqual([]);
  }

  expect(pageErrors).toEqual([]);
});
