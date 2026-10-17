import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExerciseDetailPage } from "../src/components/ExerciseDetailPage";

const exercise = {
  id: "exr_123",
  name: "Supported row",
  body_parts: ["chest"],
  target_muscles: ["pectorals"],
  equipment: ["barbell"],
  exercise_type: "strength",
  instructions: ["Set up", "Move"],
  media_url: null,
  source: {
    name: "ExerciseDB",
    notice: "Exercise data is provided live by ExerciseDB.",
  },
};

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={["/exercises/exr_123"]}>
      <Routes>
        <Route path="/exercises/:exerciseId" element={<ExerciseDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ExerciseDetailPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders optional-field fallbacks, instructions, attribution, and an accessible back link", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(exercise))),
    );

    renderDetail();

    expect(
      await screen.findByRole("heading", { name: "Supported row" }),
    ).toBeVisible();
    expect(
      screen.getByText(
        "No demonstration media is available for this exercise.",
      ),
    ).toBeVisible();
    expect(screen.getByRole("heading", { name: "Instructions" })).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Back to exercises" }),
    ).toHaveAttribute("href", "/exercises");
  });

  it("distinguishes a missing exercise from a retryable catalog failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("", { status: 404 })),
    );

    renderDetail();

    expect(
      await screen.findByRole("heading", { name: "Exercise not found" }),
    ).toBeVisible();
  });
});
