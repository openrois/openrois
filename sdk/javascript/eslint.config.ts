import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    // The consumer project is a fixture that has to use require and to declare what it uses
    // only for the type checker.
    ignores: ["dist/", "node_modules/", "tests/consumer/project/"],
  },
  ...tseslint.configs.recommended,
  {
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          destructuredArrayIgnorePattern: "^_",
        },
      ],
      "@typescript-eslint/no-explicit-any": "warn",
    },
  },
);