// ESLint 9 flat config. It carries over the former .eslintrc.json exactly: next/core-web-vitals +
// jsx-a11y strict, plus two documented rule options. Run with the ESLint CLI (`npm run lint`); the
// deprecated `next lint` wrapper is no longer used.
//
// eslint-config-next 15 ships eslintrc-style presets, so they are loaded through FlatCompat. Both
// presets go through the same compat call, so they share one `jsx-a11y` plugin instance (flat config
// refuses two different objects registered under one plugin name).
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

const config = [
  {
    ignores: [".next/**", "node_modules/**", "public/sw.js", "next-env.d.ts"],
  },
  ...compat.extends("next/core-web-vitals", "plugin:jsx-a11y/strict"),
  {
    rules: {
      // `<RequireSession role="student">` is a component prop naming the signed-in role, not an
      // ARIA role; DOM elements are still checked.
      "jsx-a11y/aria-role": ["error", { ignoreNonDOM: true }],
      // Label text can sit at label > span > strong > {expression}, deeper than the default depth.
      "jsx-a11y/label-has-associated-control": ["error", { assert: "either", depth: 4 }],
    },
  },
];

export default config;
