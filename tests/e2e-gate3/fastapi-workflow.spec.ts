import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Request } from "@playwright/test";
import {
  inspectPdf,
  reserveLoopbackPort,
  startGate3FastApiServer,
  type Gate3FastApiServer,
} from "./support/server";

const repositoryRoot = fileURLToPath(new URL("../../", import.meta.url));
const worksheetPath = join(
  repositoryRoot,
  "backend",
  "tests",
  "corpus",
  "01-biology-polished.pdf",
);
const exactAnswer =
  "Mitochondria release usable energy from food — this answer stays exact.";

type AssignmentProjection = {
  assignment_id: string;
  version: number;
  status: "analyzing" | "ready" | "analysis_failed";
  source: { sha256: string };
  questions: Array<{
    question_id: string;
    page_number: number;
    confirmed_answer: { exact_text: string } | null;
  }>;
};

type ExportProjection = {
  export_id: string;
  status: "creating" | "complete" | "failed";
  download_url: string | null;
};

test.describe.configure({ mode: "serial" });

test("built FastAPI app preserves an authenticated partial export across restart", async ({
  browser,
}, testInfo) => {
  const port = await reserveLoopbackPort();
  const storagePath = testInfo.outputPath("durable-storage");
  let server: Gate3FastApiServer | undefined;
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  const apiRequests: Request[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/v2/")) {
      apiRequests.push(request);
    }
  });

  try {
    server = await startGate3FastApiServer({ port, storagePath });
    const origin = server.origin;
    const initialResponse = await page.goto(`${origin}/app`);
    expect(initialResponse?.status()).toBe(200);
    expect(
      (await initialResponse?.allHeaders())?.["content-security-policy"],
    ).toContain("default-src 'self'");

    const assignmentResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/v2/assignments",
    );
    await page
      .getByLabel("Choose a PDF worksheet")
      .setInputFiles(worksheetPath);
    const assignmentResponse = await assignmentResponsePromise;
    expect(assignmentResponse.status()).toBe(201);
    const created = (await assignmentResponse.json()) as AssignmentProjection;
    if (created.status === "analyzing") {
      await expect
        .poll(
          () =>
            apiRequests.filter(
              (request) =>
                request.method() === "GET" &&
                new URL(request.url()).pathname ===
                  `/api/v2/assignments/${created.assignment_id}`,
            ).length,
        )
        .toBeGreaterThan(0);
    }

    const setCookie = (await assignmentResponse.allHeaders())["set-cookie"];
    expect(setCookie).toContain("HttpOnly");
    expect(setCookie).toContain("Secure");
    expect(setCookie).toContain("SameSite=lax");
    const ownerCookie = (await context.cookies(origin)).find(
      (cookie) => cookie.name === "claros_gate3_owner",
    );
    expect(ownerCookie).toMatchObject({
      httpOnly: true,
      secure: true,
      sameSite: "Lax",
    });
    expect(await page.evaluate(() => document.cookie)).not.toContain(
      "claros_gate3_owner",
    );

    await expect(
      page.getByRole("heading", { level: 2, name: "01-biology-polished" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Start Question 1" }).click();
    await expect(page).toHaveURL(`${origin}/app/${created.assignment_id}`);
    await expect(
      page.getByRole("heading", {
        level: 1,
        name: /What organelle releases usable energy from food/,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("img", { name: /original worksheet excerpt/i }),
    ).toBeVisible();

    const question = created.questions[0];
    const sourceRange = await page.evaluate(
      async ({ assignmentId }) => {
        const response = await fetch(
          `/api/v2/assignments/${encodeURIComponent(assignmentId)}/source`,
          { headers: { Range: "bytes=0-31" } },
        );
        return {
          status: response.status,
          acceptRanges: response.headers.get("accept-ranges"),
          contentRange: response.headers.get("content-range"),
          bytes: Array.from(new Uint8Array(await response.arrayBuffer())),
        };
      },
      { assignmentId: created.assignment_id },
    );
    expect(sourceRange).toMatchObject({
      status: 206,
      acceptRanges: "bytes",
    });
    expect(sourceRange.contentRange).toMatch(/^bytes 0-31\/\d+$/);
    expect(String.fromCharCode(...sourceRange.bytes.slice(0, 5))).toBe("%PDF-");

    const pageContext = await page.evaluate(
      async ({ assignmentId, questionId, pageNumber }) => {
        const response = await fetch(
          `/api/v2/assignments/${encodeURIComponent(assignmentId)}/pages/${pageNumber}/context?question_id=${encodeURIComponent(questionId)}`,
        );
        return { status: response.status, body: await response.json() };
      },
      {
        assignmentId: created.assignment_id,
        questionId: question.question_id,
        pageNumber: question.page_number,
      },
    );
    expect(pageContext.status).toBe(200);
    expect(pageContext.body).toMatchObject({
      question_id: question.question_id,
      page_number: question.page_number,
      source_sha256: created.source.sha256,
      source_status: "original",
      source_url: `/api/v2/assignments/${created.assignment_id}/source`,
      crop: {
        x_mpt: expect.any(Number),
        y_mpt: expect.any(Number),
        width_mpt: expect.any(Number),
        height_mpt: expect.any(Number),
      },
    });
    expect(pageContext.body.crop.width_mpt).toBeGreaterThan(0);
    expect(pageContext.body.crop.height_mpt).toBeGreaterThan(0);

    await page.getByRole("button", { name: "Type instead" }).click();
    await page.getByRole("textbox", { name: "Your words" }).fill(exactAnswer);
    await page.getByRole("button", { name: "Review answer" }).click();
    await expect(
      page.getByRole("heading", { level: 1, name: "Review your exact answer" }),
    ).toBeVisible();
    await expect(page.getByText(exactAnswer, { exact: true })).toBeVisible();

    await page.getByRole("button", { name: "Use this exact answer" }).click();
    await expect(
      page.getByRole("heading", {
        level: 1,
        name: "Answer added to the worksheet.",
      }),
    ).toBeVisible();
    await page.getByRole("link", { name: "Review answers" }).click();
    await expect(page).toHaveURL(
      `${origin}/app/${created.assignment_id}/review`,
    );
    await expect(page.locator(".v2-task").getByRole("status")).toContainText(
      "1 of 2 answered. Unanswered questions will stay blank.",
    );

    await page.getByRole("button", { name: "Download completed PDF" }).click();
    await expect(
      page.getByRole("heading", {
        level: 1,
        name: "Your completed PDF is ready",
      }),
    ).toBeVisible();
    const exportUrl = new URL(page.url());
    const exportId = exportUrl.pathname.split("/").at(-1);
    expect(exportId).toBeTruthy();

    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download completed PDF" }).click();
    const download = await downloadPromise;
    const downloadPath = testInfo.outputPath(download.suggestedFilename());
    await download.saveAs(downloadPath);
    const downloadedBytes = await readFile(downloadPath);
    expect(downloadedBytes.subarray(0, 5).toString("ascii")).toBe("%PDF-");
    expect(downloadedBytes.length).toBeGreaterThan(1_000);
    expect(inspectPdf(downloadPath)).toMatchObject({
      pageCount: expect.any(Number),
      warnings: [],
    });

    const cookieBeforeRestart = ownerCookie?.value;
    await server.stop();
    server = undefined;
    server = await startGate3FastApiServer({ port, storagePath });
    await page.reload();
    await expect(
      page.getByRole("heading", {
        level: 1,
        name: "Your completed PDF is ready",
      }),
    ).toBeVisible();

    const restored = await page.evaluate(
      async ({ assignmentId, exportId }) => {
        const assignmentResponse = await fetch(
          `/api/v2/assignments/${encodeURIComponent(assignmentId)}`,
        );
        const exportResponse = await fetch(
          `/api/v2/assignments/${encodeURIComponent(assignmentId)}/exports/${encodeURIComponent(exportId)}`,
        );
        return {
          assignmentStatus: assignmentResponse.status,
          assignment: await assignmentResponse.json(),
          exportStatus: exportResponse.status,
          exported: await exportResponse.json(),
        };
      },
      { assignmentId: created.assignment_id, exportId: exportId! },
    );
    expect(restored.assignmentStatus).toBe(200);
    expect(restored.exportStatus).toBe(200);
    const restoredAssignment = restored.assignment as AssignmentProjection;
    const restoredExport = restored.exported as ExportProjection;
    expect(restoredAssignment.status).toBe("ready");
    expect(restoredAssignment.source.sha256).toBe(created.source.sha256);
    expect(
      restoredAssignment.questions.filter(
        (item) => item.confirmed_answer !== null,
      ),
    ).toHaveLength(1);
    expect(restoredAssignment.questions[0].confirmed_answer?.exact_text).toBe(
      exactAnswer,
    );
    expect(restoredExport).toMatchObject({
      export_id: exportId,
      status: "complete",
    });
    expect(restoredExport.download_url).toBe(
      `/api/v2/assignments/${created.assignment_id}/exports/${exportId}/download`,
    );
    expect(
      (await context.cookies(origin)).find(
        (cookie) => cookie.name === "claros_gate3_owner",
      )?.value,
    ).toBe(cookieBeforeRestart);

    const stranger = await browser.newContext();
    try {
      const denied = await stranger.request.get(
        `${origin}/api/v2/assignments/${created.assignment_id}`,
      );
      expect(denied.status()).toBe(404);
      expect(await denied.json()).toMatchObject({
        error: { code: "assignment_not_found", recoverable: false },
      });
    } finally {
      await stranger.close();
    }

    const mutationRequests = apiRequests.filter((request) =>
      ["POST", "PATCH", "PUT", "DELETE"].includes(request.method()),
    );
    expect(mutationRequests.length).toBeGreaterThanOrEqual(4);
    for (const request of mutationRequests) {
      expect(new URL(request.url()).origin).toBe(origin);
      const headers = await request.allHeaders();
      expect(headers.origin).toBe(origin);
      expect(headers["sec-fetch-site"]).toBe("same-origin");
    }
  } catch (error) {
    if (server) {
      await testInfo.attach("fastapi-server-log", {
        body: server.logs(),
        contentType: "text/plain",
      });
    }
    throw error;
  } finally {
    await server?.stop();
    await context.close();
  }
});
