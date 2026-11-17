import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Story's server runs on 8777; the dev server proxies the API to it.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8777", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
