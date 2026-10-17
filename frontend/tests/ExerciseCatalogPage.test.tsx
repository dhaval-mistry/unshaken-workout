import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExerciseCatalogPage } from "../src/components/ExerciseCatalogPage";

const exercise = {
  id: "exr_123",
  name: "Supported row",
  body_parts: ["chest"],
  target_muscles: ["pectorals"],
  equipment: ["barbell"],
  exercise_type: "strength",
  instructions: ["Set up"],
  media_url: null,
  source: {
    name: "ExerciseDB",
    notice: "Exercise data is provided live by ExerciseDB.",
  },
};

function renderCatalog() {
  return render(
    <MemoryRouter>
      <ExerciseCatalogPage />
    </MemoryRouter>,
  );
}

describe("ExerciseCatalogPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows loading then searchable normalized results with keyboard-navigable details", async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            items: [exercise],
            page: 1,
            page_size: 20,
            total: 1,
          }),
        ),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderCatalog();
    expect(screen.getByRole("status")).toHaveTextContent("Loading exercises…");
    await screen.findByRole("link", { name: "Supported row" });
    await user.type(screen.getByLabelText("Exercise name"), "press");
    await user.click(screen.getByRole("button", { name: "Search exercises" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining("query=press"),
        expect.any(Object),
      ),
    );
    expect(screen.getByRole("link", { name: "Supported row" })).toHaveAttribute(
      "href",
      "/exercises/exr_123",
    );
    expect(
      screen.getByText("Exercise data is provided live by ExerciseDB."),
    ).toBeVisible();
  });

  it("offers a clear empty result state", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ items: [], page: 1, page_size: 20, total: 0 }),
          ),
        ),
    );

    renderCatalog();

    expect(
      await screen.findByText(
        "No exercises match these filters. Try a broader search.",
      ),
    ).toBeVisible();
  });

  it("shows an accessible provider error and retries the request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ message: "Catalog service is unavailable." }),
          { status: 503 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [exercise],
            page: 1,
            page_size: 20,
            total: 1,
          }),
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderCatalog();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Catalog service is unavailable.",
    );
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(
      await screen.findByRole("link", { name: "Supported row" }),
    ).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
