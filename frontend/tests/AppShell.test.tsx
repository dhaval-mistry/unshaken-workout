import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { AppShell } from "../src/app/AppShell";

describe("AppShell", () => {
  it("provides a keyboard skip link and named primary navigation", () => {
    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("link", { name: "Skip to content" }),
    ).toHaveAttribute("href", "#main-content");
    expect(
      screen.getByRole("navigation", { name: "Primary navigation" }),
    ).toBeVisible();
  });
});
