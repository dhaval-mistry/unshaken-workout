import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { AppShell } from "./AppShell";
import { RouteErrorPage } from "./RouteErrorPage";
import { HomePage } from "../components/HomePage";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteErrorPage />,
    children: [{ index: true, element: <HomePage /> }],
  },
]);

/** Provides the browser router and its route-level recovery screen. */
export function AppRouter() {
  return <RouterProvider router={router} />;
}
