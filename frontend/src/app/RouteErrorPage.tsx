import { isRouteErrorResponse, useRouteError } from "react-router-dom";

/** Shows a stable, accessible recovery screen for unexpected route failures. */
export function RouteErrorPage() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `The requested page returned ${error.status}.`
    : "We could not load this page.";

  return (
    <main className="route-error" aria-labelledby="route-error-title">
      <p className="eyebrow">Unshaken</p>
      <h1 id="route-error-title">Something needs another try</h1>
      <p role="alert">{message}</p>
      <a className="button" href="/">
        Return home
      </a>
    </main>
  );
}
