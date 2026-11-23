import vue from "@vitejs/plugin-vue";
import vuetify from "vite-plugin-vuetify";
import { defineConfig } from "vitest/config";

// https://vite.dev/config/ and https://vitest.dev/config/
export default defineConfig({
  plugins: [vue(), vuetify({ autoImport: true })],
  // The end-to-end tests build with the source maps inside the files, so the coverage they
  // collect from the browser can be mapped back to src/ (see docs/how-to/development.md).
  build: {
    // Fonts and images stay files. Inlined as data: URLs they would need `data:` in the
    // container's font-src, and the Content-Security-Policy allows only the app's own files.
    assetsInlineLimit: 0,
    sourcemap: process.env["BLINDSPOT_SOURCEMAP"] === "inline" ? "inline" : false,
  },
  // In development and in the host-mode tests the API runs on its own port; in the container
  // nginx serves both.
  // The Host header is passed on as the browser sent it, as nginx does: the API compares it with
  // the Origin of every request that changes something (and passkeys belong to it).
  server: { proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } } },
  preview: { proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["tests/setup.ts"],
    include: ["tests/**/*.test.ts"],
    server: { deps: { inline: ["vuetify"] } },
    css: false,
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,vue}"],
      reporter: ["text", "lcov", "html"],
      // Target 100%; the build fails below 95%.
      thresholds: { statements: 95, branches: 95, functions: 95, lines: 95 },
    },
  },
});
