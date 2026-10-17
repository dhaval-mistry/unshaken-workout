import { NavLink, Outlet } from "react-router-dom";

/** Shared accessible page frame for the catalog and future approved routes. */
export function AppShell() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="site-header">
        <NavLink className="brand" to="/" aria-label="Unshaken home">
          Unshaken
        </NavLink>
        <nav aria-label="Primary navigation">
          <NavLink to="/exercises">Exercises</NavLink>
        </nav>
      </header>
      <main id="main-content" className="site-main" tabIndex={-1}>
        <Outlet />
      </main>
      <footer className="site-footer">Technical foundation — Phase 1</footer>
    </div>
  );
}
