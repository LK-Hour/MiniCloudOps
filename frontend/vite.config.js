import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";

const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8"));

// In dev, /api calls go to the gateway started by Docker Compose.
export default defineConfig({
  plugins: [react()],
  // Build information for the About page.
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
    __BUILD_SHA__: JSON.stringify(process.env.GIT_SHA || "dev"),
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  server: {
    port: 5173,
    proxy: {
      "/api": process.env.VITE_GATEWAY_URL || "http://localhost:8080",
    },
  },
});
