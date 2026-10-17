import { createBrowserRouter, RouterProvider } from "react-router-dom";

import { AppShell } from "./AppShell";
import { RouteErrorPage } from "./RouteErrorPage";
import { HomePage } from "../components/HomePage";
import { ExerciseCatalogPage } from "../components/ExerciseCatalogPage";
import { ExerciseDetailPage } from "../components/ExerciseDetailPage";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteErrorPage />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "exercises", element: <ExerciseCatalogPage /> },
      { path: "exercises/:exerciseId", element: <ExerciseDetailPage /> },
    ],
  },
]);

/** Provides the browser router and its route-level recovery screen. */
export function AppRouter() {
  return <RouterProvider router={router} />;
}
