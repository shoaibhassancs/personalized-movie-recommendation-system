/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// strictPort: if 5173 is busy, fail loudly. The API allows exactly
// http://localhost:5173 (CORS), so a silent move to 5174 would break every call.
// Only variables named VITE_* reach the browser bundle. Never name a secret that way.
export default defineConfig({
  plugins: [react()],
  server: { host: "localhost", port: 5173, strictPort: true },
  preview: { host: "localhost", port: 5173, strictPort: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
