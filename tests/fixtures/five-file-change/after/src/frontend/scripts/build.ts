/**
 * Production build of the frontend into src/frontend/dist (the folder the Tauri app embeds).
 * `--debug`: not minified, so breakpoints and variable names in the debugger match the source (`npm run debug:build`).
 */
import { build } from "esbuild";
import { bundleOptions, dist, prepareDist } from "./lib/frontend-build.ts";

prepareDist();
await build(bundleOptions(!process.argv.includes("--debug")));
console.log(`frontend built -> ${dist}`);
