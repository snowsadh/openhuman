import { defineConfig } from "orval";

export default defineConfig({
  api: {
    input: {
      target: "../../apps/api/openapi.json",
      validation: false,
    },
    output: {
      mode: "tags-split",
      target: "src/api",
      schemas: "src/schemas",
      client: "react-query",
      clean: true,
      prettier: true,
      override: {
        mutator: {
          path: "src/mutator/custom-instance.ts",
          name: "customInstance",
        },
      },
    },
    hooks: {
      afterAllFilesWrite: "prettier --write",
    },
  },
});
