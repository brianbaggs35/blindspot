import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";
import vuetify from "vite-plugin-vuetify";

// https://vite.dev/config/ and https://vitest.dev/config/
export default defineConfig({
  plugins: [vue(), vuetify({ autoImport: true })],
  build: {
    // Fonts and images stay files. Inlined as data: URLs they would need `data:` in the
    // container's font-src, and the Content-Security-Policy allows only the app's own files.
    assetsInlineLimit: 0,
  },
  server: {
    // In development the API runs on its own port; in the container nginx serves both.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
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
