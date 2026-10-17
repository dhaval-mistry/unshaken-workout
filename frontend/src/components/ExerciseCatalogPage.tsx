import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { getExercises } from "../api/exercises";
import type { Exercise, ExerciseFilters } from "../api/exercises";

const initialFilters: ExerciseFilters = {
  query: "",
  bodyPart: "",
  equipment: "",
  exerciseType: "",
  page: 1,
  pageSize: 20,
};

function details(exercise: Exercise): string {
  const bodyPart = exercise.body_parts[0] ?? "Body area not listed";
  const target = exercise.target_muscles[0] ?? "Target muscle not listed";
  return `${bodyPart} · ${target}`;
}

/** Accessible live catalog with explicit search submission and retry rather than hidden provider calls. */
export function ExerciseCatalogPage() {
  const [filters, setFilters] = useState(initialFilters);
  const [appliedFilters, setAppliedFilters] = useState(initialFilters);
  const [items, setItems] = useState<Exercise[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    setErrorMessage("");
    void getExercises(appliedFilters, controller.signal)
      .then((page) => {
        setItems(page.items);
        setTotal(page.total);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : "The exercise catalog could not be loaded. Please try again.",
          );
          setState("error");
        }
      });
    return () => controller.abort();
  }, [appliedFilters]);

  function updateFilter(name: keyof ExerciseFilters, value: string) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedFilters({ ...filters, page: 1 });
  }

  function changePage(page: number) {
    const next = { ...appliedFilters, page };
    setFilters(next);
    setAppliedFilters(next);
  }

  const hasNextPage =
    total === null
      ? items.length === appliedFilters.pageSize
      : appliedFilters.page * appliedFilters.pageSize < total;

  return (
    <section className="catalog-page" aria-labelledby="catalog-title">
      <p className="eyebrow">Exercise library</p>
      <h1 id="catalog-title">Find a movement that fits.</h1>
      <p>
        Search the live standard catalog. Exercise content is provided by
        ExerciseDB.
      </p>

      <form
        className="catalog-filters"
        onSubmit={search}
        aria-label="Search exercises"
      >
        <label>
          Exercise name
          <input
            name="query"
            value={filters.query}
            onChange={(event) => updateFilter("query", event.target.value)}
            type="search"
          />
        </label>
        <label>
          Body area
          <input
            name="bodyPart"
            value={filters.bodyPart}
            onChange={(event) => updateFilter("bodyPart", event.target.value)}
          />
        </label>
        <label>
          Equipment
          <input
            name="equipment"
            value={filters.equipment}
            onChange={(event) => updateFilter("equipment", event.target.value)}
          />
        </label>
        <label>
          Exercise type
          <input
            name="exerciseType"
            value={filters.exerciseType}
            onChange={(event) =>
              updateFilter("exerciseType", event.target.value)
            }
          />
        </label>
        <button type="submit">Search exercises</button>
      </form>

      {state === "loading" && <p role="status">Loading exercises…</p>}
      {state === "error" && (
        <div className="notice notice--error" role="alert">
          <p>{errorMessage}</p>
          <button
            type="button"
            onClick={() => setAppliedFilters({ ...appliedFilters })}
          >
            Try again
          </button>
        </div>
      )}
      {state === "ready" && items.length === 0 && (
        <p role="status">
          No exercises match these filters. Try a broader search.
        </p>
      )}
      {state === "ready" && items.length > 0 && (
        <>
          <p className="result-summary" aria-live="polite">
            {total === null
              ? `${items.length} exercises on this page`
              : `${total} exercises found`}
          </p>
          <ul className="exercise-list" aria-label="Exercise results">
            {items.map((exercise) => (
              <li key={exercise.id} className="exercise-card">
                <h2>
                  <Link to={`/exercises/${encodeURIComponent(exercise.id)}`}>
                    {exercise.name}
                  </Link>
                </h2>
                <p>{details(exercise)}</p>
                <p className="source-notice">{exercise.source.notice}</p>
              </li>
            ))}
          </ul>
          <nav className="pagination" aria-label="Exercise result pages">
            <button
              type="button"
              disabled={appliedFilters.page === 1}
              onClick={() => changePage(appliedFilters.page - 1)}
            >
              Previous page
            </button>
            <span>Page {appliedFilters.page}</span>
            <button
              type="button"
              disabled={!hasNextPage}
              onClick={() => changePage(appliedFilters.page + 1)}
            >
              Next page
            </button>
          </nav>
        </>
      )}
    </section>
  );
}
