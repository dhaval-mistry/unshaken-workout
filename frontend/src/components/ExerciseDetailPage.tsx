import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ExerciseApiError, getExercise } from "../api/exercises";
import type { Exercise } from "../api/exercises";

function field(values: string[]): string {
  return values.length > 0 ? values.join(", ") : "Not listed";
}

/** Renders resilient normalized details; media remains optional because provider permissions can change. */
export function ExerciseDetailPage() {
  const { exerciseId } = useParams();
  const [exercise, setExercise] = useState<Exercise | null>(null);
  const [state, setState] = useState<
    "loading" | "ready" | "error" | "not-found"
  >("loading");
  const [errorMessage, setErrorMessage] = useState("");

  const load = useCallback(() => {
    if (!exerciseId) return;
    setState("loading");
    void getExercise(exerciseId)
      .then((result) => {
        setExercise(result);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof ExerciseApiError && error.status === 404) {
          setState("not-found");
          return;
        }
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "The exercise details could not be loaded. Please try again.",
        );
        setState("error");
      });
  }, [exerciseId]);

  useEffect(() => {
    load();
  }, [load]);

  if (state === "loading")
    return <p role="status">Loading exercise details…</p>;
  if (state === "not-found")
    return (
      <section className="notice notice--error">
        <h1>Exercise not found</h1>
        <p>This exercise is no longer available from the catalog.</p>
        <Link className="button" to="/exercises">
          Back to exercises
        </Link>
      </section>
    );
  if (state === "error")
    return (
      <section className="notice notice--error" role="alert">
        <h1>Exercise details unavailable</h1>
        <p>{errorMessage}</p>
        <button type="button" onClick={load}>
          Try again
        </button>
      </section>
    );
  if (exercise === null) return null;

  return (
    <article className="exercise-detail" aria-labelledby="exercise-title">
      <Link className="back-link" to="/exercises">
        Back to exercises
      </Link>
      <p className="eyebrow">Standard exercise</p>
      <h1 id="exercise-title">{exercise.name}</h1>
      {exercise.media_url ? (
        <img
          className="exercise-media"
          src={exercise.media_url}
          alt={`${exercise.name} exercise demonstration`}
        />
      ) : (
        <p className="media-fallback">
          No demonstration media is available for this exercise.
        </p>
      )}
      <dl className="exercise-facts">
        <div>
          <dt>Body area</dt>
          <dd>{field(exercise.body_parts)}</dd>
        </div>
        <div>
          <dt>Target muscle</dt>
          <dd>{field(exercise.target_muscles)}</dd>
        </div>
        <div>
          <dt>Equipment</dt>
          <dd>{field(exercise.equipment)}</dd>
        </div>
        <div>
          <dt>Exercise type</dt>
          <dd>{exercise.exercise_type ?? "Not listed"}</dd>
        </div>
      </dl>
      <section aria-labelledby="instructions-title">
        <h2 id="instructions-title">Instructions</h2>
        {exercise.instructions.length > 0 ? (
          <ol>
            {exercise.instructions.map((instruction, index) => (
              <li key={`${index}-${instruction}`}>{instruction}</li>
            ))}
          </ol>
        ) : (
          <p>Instructions are not available for this exercise.</p>
        )}
      </section>
      <p className="source-notice">{exercise.source.notice}</p>
    </article>
  );
}
