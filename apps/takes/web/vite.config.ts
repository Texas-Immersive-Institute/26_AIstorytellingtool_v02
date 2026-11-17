import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Takes' server runs on 8778; the dev server proxies the API to it.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5175,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8778" },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
