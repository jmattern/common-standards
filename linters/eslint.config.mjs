import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["**/node_modules/**", "**/dist/**", "**/build/**", "**/.*/*"],
  },
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{js,mjs,cjs,jsx,ts,tsx}"],
    rules: {
      "no-debugger": "error",
      "no-duplicate-imports": "error",
      "no-unreachable": "error",
    },
  },
  {
    files: ["**/*.{js,mjs,cjs,jsx}"],
    rules: {"no-unused-vars": ["error", { argsIgnorePattern: "^_" }]},
  },
  {
    files: ["**/*.{ts,tsx}"],
    rules: {"@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }]},
  },
);
