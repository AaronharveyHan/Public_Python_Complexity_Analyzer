import axios from "axios";

// In dev mode Vite proxies /analyze etc. to localhost:8000 (see vite.config.js).
// In preview / production builds set VITE_API_BASE=http://localhost:8000 before
// running `npm run build`, or the preview server uses its own proxy (same config).
const BASE = import.meta.env.VITE_API_BASE ?? "";

// WebSocket base: derive from BASE if set; otherwise use the page's own host
// so the proxy path (/ws/...) is forwarded the same way as /result etc.
const WS_BASE = BASE
  ? BASE.replace(/^http/, "ws")
  : `${typeof window !== "undefined" && window.location.protocol === "https:" ? "wss" : "ws"}://${typeof window !== "undefined" ? window.location.host : "localhost"}`;

export const api = {
  health: () =>
    axios.get(`${BASE}/health`),

  analyze: (projectPath, ignoreDirs = null) =>
    axios.post(`${BASE}/analyze`, { project_path: projectPath, ignore_dirs: ignoreDirs }),

  result: (taskId) =>
    axios.get(`${BASE}/result/${taskId}`),

  tasks: () =>
    axios.get(`${BASE}/tasks`),

  /** Returns the URL for downloading the HTML report (no fetch needed — used as href). */
  reportUrl: (taskId) => `${BASE}/report/${taskId}`,

  /** Returns the WebSocket URL for real-time progress. */
  wsUrl: (taskId) => `${WS_BASE}/ws/${taskId}`,
};
