// The one way the screen reaches One's core. `path` is the core's own route ("/projects", "/chat"…). In development the
// Vite server forwards /api to the core with the launch secret, so the page never holds it. The installed app will send
// the same call through a Tauri command (Plan 8 Task 2), behind this same function, so no screen calls fetch itself.

export function api(path: string, init?: RequestInit): Promise<Response> {
  return fetch("/api" + path, init);
}
