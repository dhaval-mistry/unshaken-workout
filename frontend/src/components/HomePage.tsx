import { HealthStatus } from "./HealthStatus";

/** Explains the deliberately small surface area available before product features begin. */
export function HomePage() {
  return (
    <section className="welcome-panel" aria-labelledby="welcome-title">
      <p className="eyebrow">Phase 1 foundation</p>
      <h1 id="welcome-title">A steady base for intentional training.</h1>
      <p>
        Unshaken is preparing a private workout-planning experience. Account
        access, exercise discovery, and training plans are not enabled in this
        foundation release.
      </p>
      <HealthStatus />
    </section>
  );
}
