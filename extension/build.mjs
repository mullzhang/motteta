import { build } from "esbuild";
import { mkdir, copyFile, rm } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { extensionRoot, generateAdapters } from "./generate-adapters.mjs";

export async function buildExtension(root = extensionRoot) {
  await generateAdapters({ root });
  const output = join(root, "dist");
  await rm(output, { recursive: true, force: true });
  await mkdir(output, { recursive: true });
  await build({ absWorkingDir: root, entryPoints: { background: "src/background/index.ts", content: "src/content/index.ts", popup: "src/popup/index.ts" }, bundle: true, outdir: output, format: "iife", target: "chrome120", sourcemap: false });
  await copyFile(join(root, "manifest.json"), join(output, "manifest.json"));
  await copyFile(join(root, "src/popup/popup.html"), join(output, "popup.html"));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) await buildExtension();
