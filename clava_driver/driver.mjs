#!/usr/bin/env node
// Clava classic-CLI aspect that writes one normalized Flang header inventory.

import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";


function requiredEnvironment(name) {
  const value = process.env[name];
  if (!value) throw new Error(`missing required environment variable ${name}`);
  return value;
}


async function main() {
  const repoRoot = path.resolve(requiredEnvironment("FLANG_GENERATOR_REPO_ROOT"));
  const analyzer = path.join(repoRoot, "generator", "analyze.js");
  const model = path.resolve(requiredEnvironment("FLANG_GENERATOR_MODEL_OUT"));
  const header = path.resolve(requiredEnvironment("FLANG_GENERATOR_HEADER"));
  const headerRoot = path.resolve(requiredEnvironment("FLANG_GENERATOR_HEADER_ROOT"));
  const queryModule = path.resolve(requiredEnvironment("FLANG_GENERATOR_QUERY_MODULE"));

  for (const [label, file] of [
    ["Clava analyzer", analyzer],
    ["header", header],
    ["Query module", queryModule],
  ]) {
    if (!fs.existsSync(file)) throw new Error(`${label} does not exist: ${file}`);
  }
  if (!fs.statSync(header).isFile()) throw new Error(`header is not a file: ${header}`);
  if (!fs.statSync(queryModule).isFile()) throw new Error(`Query module is not a file: ${queryModule}`);
  fs.mkdirSync(path.dirname(model), { recursive: true });
  fs.rmSync(model, { force: true });

  console.log(`[clava-driver] Analyzing ${header}`);
  try {
    await import(pathToFileURL(analyzer).href);
  } catch (error) {
    throw new Error(`Clava declaration analysis failed: ${error instanceof Error ? error.message : String(error)}`, { cause: error });
  }
  if (!fs.existsSync(model)) throw new Error(`Clava analysis completed without writing ${model}`);
  console.log(`[clava-driver] Wrote inventory ${model}`);
}


await main();
