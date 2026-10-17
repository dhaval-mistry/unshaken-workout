import { HealthStatus } from "./HealthStatus";
import { Link } from "react-router-dom";

/** Introduces the approved catalog while later planning features remain intentionally unavailable. */
export function HomePage() {
  return (
    <section className="welcome-panel" aria-labelledby="welcome-title">
      <p className="eyebrow">Phase 1 foundation</p>
      <h1 id="welcome-title">A steady base for intentional training.</h1>
      <p>
        Unshaken is preparing a private workout-planning experience. Explore the
        standard exercise library while account access and training plans remain
        intentionally unavailable.
      </p>
      <Link className="button" to="/exercises">
        Browse exercises
      </Link>
      <HealthStatus />
    </section>
  );
}
