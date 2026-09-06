import { apiBaseUrl } from "./config";

export interface HealthResponse {
  status: "ok";
}

/** Requests API liveness without sending user data or authentication state. */
export async function getApiHealth(
  signal?: AbortSignal,
): Promise<HealthResponse> {
  const response = await fetch(`${apiBaseUrl}/health/live`, { signal });

  if (!response.ok) {
    throw new Error(`Health request failed with status ${response.status}`);
  }

  return (await response.json()) as HealthResponse;
}
