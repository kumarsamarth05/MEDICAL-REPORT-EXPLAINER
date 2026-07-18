/**
 * config.example.js
 *
 * Copy this file to `config.js` (same folder) and adjust for your
 * environment. `config.js` is gitignored so each environment (local /
 * staging / production) can point at a different backend without
 * touching tracked source files or app.js.
 *
 * index.html loads config.js BEFORE app.js, so window.APP_CONFIG is
 * already set by the time app.js runs.
 */
window.APP_CONFIG = {
  // Base URL of the FastAPI backend (no trailing slash).
  API_BASE: "http://127.0.0.1:8000",
};
