import { apiBaseUrl } from "./config";

export interface ExerciseSource {
  name: "ExerciseDB";
  notice: string;
}

export interface Exercise {
  id: string;
  name: string;
  body_parts: string[];
  target_muscles: string[];
  equipment: string[];
  exercise_type: string | null;
  instructions: string[];
  media_url: string | null;
  source: ExerciseSource;
}

export interface ExercisePage {
  items: Exercise[];
  page: number;
  page_size: number;
  total: number | null;
}

export interface ExerciseFilters {
  query: string;
  bodyPart: string;
  equipment: string;
  exerciseType: string;
  page: number;
  pageSize: number;
}

export class ExerciseApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ExerciseApiError";
  }
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, { signal });
  if (!response.ok) {
    let message = "The exercise catalog could not be loaded. Please try again.";
    try {
      const body = (await response.json()) as {
        message?: unknown;
        detail?: unknown;
      };
      if (typeof body.message === "string") message = body.message;
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // The API may return an empty proxy error response; retain an accessible fallback.
    }
    throw new ExerciseApiError(message, response.status);
  }
  return (await response.json()) as T;
}

/** Requests normalized catalog content from Unshaken's API, never from ExerciseDB in the browser. */
export async function getExercises(
  filters: ExerciseFilters,
  signal?: AbortSignal,
): Promise<ExercisePage> {
  const parameters = new URLSearchParams({
    page: String(filters.page),
    page_size: String(filters.pageSize),
  });
  if (filters.query) parameters.set("query", filters.query);
  if (filters.bodyPart) parameters.set("body_part", filters.bodyPart);
  if (filters.equipment) parameters.set("equipment", filters.equipment);
  if (filters.exerciseType)
    parameters.set("exercise_type", filters.exerciseType);
  return request<ExercisePage>(
    `/api/exercises?${parameters.toString()}`,
    signal,
  );
}

/** Uses a provider identifier only through FastAPI's fixed detail route. */
export function getExercise(
  exerciseId: string,
  signal?: AbortSignal,
): Promise<Exercise> {
  return request<Exercise>(
    `/api/exercises/${encodeURIComponent(exerciseId)}`,
    signal,
  );
}
