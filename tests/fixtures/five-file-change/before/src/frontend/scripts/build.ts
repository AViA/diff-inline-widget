/** Production build of the frontend into src/frontend/dist (the folder the Tauri app embeds). */
import { build } from "esbuild";
import { bundleOptions, dist, prepareDist } from "./lib/frontend-build.ts";

prepareDist();
await build(bundleOptions(true));
console.log(`frontend built -> ${dist}`);
