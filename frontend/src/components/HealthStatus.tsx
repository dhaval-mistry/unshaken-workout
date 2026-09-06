import { useEffect, useState } from "react";

import { getApiHealth } from "../api/health";

type ConnectionState = "checking" | "available" | "unavailable";

const stateText: Record<ConnectionState, string> = {
  checking: "Checking service connection…",
  available: "Service connection available",
  unavailable: "Service connection unavailable",
};

/** Announces API connectivity without making it a prerequisite for reading the shell. */
export function HealthStatus() {
  const [state, setState] = useState<ConnectionState>("checking");

  useEffect(() => {
    const controller = new AbortController();

    void getApiHealth(controller.signal)
      .then(() => setState("available"))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setState("unavailable");
        }
      });

    return () => controller.abort();
  }, []);

  return (
    <p
      className={`connection-status connection-status--${state}`}
      aria-live="polite"
    >
      <span aria-hidden="true" className="status-dot" />
      {stateText[state]}
    </p>
  );
}
