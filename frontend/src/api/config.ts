/** Public API origin injected by Vite; this value must never contain credentials. */
export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(
  /\/$/,
  "",
);
