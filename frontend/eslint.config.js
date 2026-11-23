import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import security from "eslint-plugin-security";
import vue from "eslint-plugin-vue";
import vueA11y from "eslint-plugin-vuejs-accessibility";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "dist-e2e", "coverage", "e2e-results", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...vue.configs["flat/recommended"],
  ...vueA11y.configs["flat/recommended"],
  security.configs.recommended,
  {
    files: ["**/*.{ts,vue}"],
    languageOptions: {
      globals: { ...globals.browser },
      parserOptions: {
        projectService: true,
        extraFileExtensions: [".vue"],
        parser: tseslint.parser,
      },
    },
  },
  {
    files: ["**/*.vue"],
    rules: { "vue/multi-word-component-names": "off" },
  },
  {
    files: ["eslint.config.js", "vite.config.ts", "e2e/scripts/*.mjs"],
    ...tseslint.configs.disableTypeChecked,
  },
  {
    // The end-to-end tests and their scripts run in Node, not the browser.
    files: ["e2e/**/*.{ts,mjs}", "playwright.config.ts"],
    languageOptions: { globals: { ...globals.node } },
  },
  prettier,
);
