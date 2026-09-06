import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HealthStatus } from "../src/components/HealthStatus";

describe("HealthStatus", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("announces an available API connection", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response('{"status":"ok"}')),
    );

    render(<HealthStatus />);

    await waitFor(() =>
      expect(screen.getByText("Service connection available")).toBeVisible(),
    );
  });

  it("announces a recoverable unavailable connection", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("", { status: 503 })),
    );

    render(<HealthStatus />);

    await waitFor(() =>
      expect(screen.getByText("Service connection unavailable")).toBeVisible(),
    );
  });
});
