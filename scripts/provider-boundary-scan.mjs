#!/usr/bin/env node

import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

const roots = ["src", "scripts", "runpod"].map((directory) => path.resolve(directory));
const self = path.resolve(process.argv[1]);
const runnableExtensions = new Set([
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
  ".ts",
  ".tsx",
  ".mts",
  ".py",
  ".sh",
  ".json",
  ".toml",
  ".yaml",
  ".yml",
]);
const runnableBasenames = new Set(["Dockerfile"]);
const forbidden = [
  ["celeb", "makerai-backend"].join(""),
  ["ZImage", "NsfwService"].join(""),
  ["/dev/celeb", "maker"].join(""),
  ["/dev/nextmedia", "-seeder"].join(""),
];

async function files(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async (entry) => {
    const target = path.join(directory, entry.name);
    return entry.isDirectory() ? files(target) : [target];
  }));
  return nested.flat();
}

const violations = [];
for (const file of (await Promise.all(roots.map(files))).flat()) {
  if (
    path.resolve(file) === self
    || (!runnableExtensions.has(path.extname(file)) && !runnableBasenames.has(path.basename(file)))
  ) continue;
  const source = await readFile(file, "utf8");
  for (const token of forbidden) {
    if (source.includes(token)) violations.push(`${path.relative(process.cwd(), file)}: ${token}`);
  }
}

if (violations.length > 0) {
  process.stderr.write(`Cross-product provider boundary violations:\n${violations.join("\n")}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write("Provider boundary scan passed.\n");
}
