// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AppProviders } from "../src/v2/AppProviders";
import RootApp from "../src/v2/RootApp";

vi.mock("../src/v2/document/DocumentCrop", () => ({
  default: () => <div data-testid="document-crop">Authentic document crop</div>,
}));

vi.mock("../src/v2/document/WorksheetDialog", () => ({
  default: () => (
    <div role="dialog" aria-label="Worksheet">
      Worksheet viewer
    </div>
  ),
}));

await Promise.all([
  import("../src/v2/WorkspaceShell"),
  import("../src/ui/App"),
]);

afterEach(cleanup);

function renderRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppProviders>
        <RootApp />
      </AppProviders>
    </MemoryRouter>,
  );
}

describe("V2 route shell", () => {
  it("renders the marketing route without a fabricated worksheet", () => {
    const { container } = renderRoute("/");

    expect(
      screen.getByRole("heading", {
        name: "The answer is yours. Getting it onto the page can be easier.",
      }),
    ).toBeInTheDocument();
    expect(container.querySelector("canvas")).not.toBeInTheDocument();
    expect(container.querySelector("iframe")).not.toBeInTheDocument();
  });

  it("renders the empty /app route without a source document", async () => {
    renderRoute("/app");

    expect(
      await screen.findByRole(
        "heading",
        { name: "Bring in a worksheet." },
        { timeout: 5_000 },
      ),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("document-crop")).not.toBeInTheDocument();
  });

  it.each([
    ["/app/assignment_123", "Why do plants need sunlight?"],
    ["/app/assignment_123/review", "Review answers"],
    ["/app/assignment_123/export/export_456", "Your completed PDF is ready"],
  ])("renders %s as a V2 workspace route", async (path, heading) => {
    renderRoute(path);

    expect(
      await screen.findByRole("heading", { name: heading }, { timeout: 5_000 }),
    ).toBeInTheDocument();
    expect(
      await screen.findByTestId("document-crop", {}, { timeout: 5_000 }),
    ).toBeInTheDocument();
  });

  it("keeps V1 available only beneath the legacy route", async () => {
    renderRoute("/legacy");

    expect(
      await screen.findByRole(
        "heading",
        {
          name: /The answer is yours\.\s*Getting it onto the page can be easier\./,
        },
        { timeout: 25_000 },
      ),
    ).toBeInTheDocument();
    expect(document.querySelector(".legacy-root")).toBeInTheDocument();
  });

  it("shows an explicit not-found screen for an unknown route", () => {
    renderRoute("/not-a-route");

    expect(
      screen.getByRole("heading", { name: "That page is not available." }),
    ).toBeInTheDocument();
  });
});
