import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Shared proxy table — used by both dev server and preview server so that
// `npm run preview` (port 4173) also forwards API calls to FastAPI.
// Note: Node 18+ resolves "localhost" as ::1 (IPv6); use 127.0.0.1 (IPv4)
// to match uvicorn's default bind address.
// changeOrigin rewrites the Host header — required for some Windows setups.
const _target = "http://127.0.0.1:8000";
const _proxy  = (target) => ({ target, changeOrigin: true });
const _wsProxy = (target) => ({ target: target.replace("http", "ws"), changeOrigin: true, ws: true });
const API_PROXY = {
  "/analyze": _proxy(_target),
  "/result":  _proxy(_target),
  "/tasks":   _proxy(_target),
  "/health":  _proxy(_target),
  "/report":  _proxy(_target),
  "/ws":      _wsProxy(_target),
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: API_PROXY,
  },
  preview: {
    port: 4173,
    proxy: API_PROXY,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-react":   ["react", "react-dom", "react-router-dom"],
          "vendor-echarts": ["echarts", "echarts-for-react"],
          "vendor-axios":   ["axios"],
        },
      },
    },
  },
});
