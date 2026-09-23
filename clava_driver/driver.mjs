#!/usr/bin/env node
// Clava classic-CLI aspect: analyze the active AST, generate probe outputs,
// then run protoc. Configuration is passed by run.sh through the environment.

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";


function requiredEnvironment(name) {
  const value = process.env[name];
  if (!value) throw new Error(`missing required environment variable ${name}`);
  return value;
}


function runChild(phase, executable, args, cwd) {
  console.log(`[clava-driver] ${phase}: ${executable} ${args.join(" ")}`);
  const result = spawnSync(executable, args, {
    cwd,
    env: process.env,
    stdio: "inherit",
  });
  if (result.error) {
    throw new Error(`${phase} could not start: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const status = result.status === null ? `signal ${result.signal}` : `exit code ${result.status}`;
    throw new Error(`${phase} failed with ${status}`);
  }
}


async function main() {
  const repoRoot = path.resolve(requiredEnvironment("FLANG_DRIVER_REPO_ROOT"));
  const clavaEntry = path.resolve(requiredEnvironment("FLANG_DRIVER_CLAVA_ENTRY"));
  const analyzer = path.join(repoRoot, "generator", "analyze.js");
  const model = path.resolve(requiredEnvironment("FLANG_DRIVER_MODEL"));
  const header = path.resolve(requiredEnvironment("FLANG_GENERATOR_HEADER"));
  const headerRoot = path.resolve(requiredEnvironment("FLANG_GENERATOR_HEADER_ROOT"));
  const queryModule = path.resolve(requiredEnvironment("FLANG_GENERATOR_QUERY_MODULE"));
  const metadata = path.resolve(requiredEnvironment("FLANG_DRIVER_METADATA"));
  const outputDir = path.resolve(requiredEnvironment("FLANG_DRIVER_OUTPUT_DIR"));
  const protoc = path.resolve(requiredEnvironment("FLANG_DRIVER_PROTOC"));
  const python = requiredEnvironment("FLANG_DRIVER_PYTHON");

  for (const [label, file] of [
    ["Clava entry", clavaEntry],
    ["Clava analyzer", analyzer],
    ["header", header],
    ["metadata", metadata],
    ["Query module", queryModule],
    ["protoc", protoc],
  ]) {
    if (!fs.existsSync(file)) throw new Error(`${label} does not exist: ${file}`);
  }
  if (!fs.statSync(header).isFile()) throw new Error(`header is not a file: ${header}`);
  if (!fs.statSync(metadata).isFile()) throw new Error(`metadata is not a file: ${metadata}`);
  if (!fs.statSync(queryModule).isFile()) throw new Error(`Query module is not a file: ${queryModule}`);
  if (!fs.statSync(protoc).isFile()) throw new Error(`protoc is not a file: ${protoc}`);
  fs.mkdirSync(outputDir, { recursive: true });

  console.log(`[clava-driver] Clava analysis: importing ${analyzer}`);
  fs.rmSync(model, { force: true });
  try {
    // analyze.js uses Query.search() against this Clava process's live AST.
    // A dynamic import waits for its complete inventory write before proceeding.
    await import(pathToFileURL(analyzer).href);
  } catch (error) {
    throw new Error(`Clava declaration analysis failed: ${error instanceof Error ? error.message : String(error)}`, { cause: error });
  }
  if (!fs.existsSync(model)) throw new Error(`Clava analysis completed without writing ${model}`);

  const generateScript = path.join(repoRoot, "generator", "generate.py");
  runChild(
    "Python generation",
    python,
    [
      generateScript,
      "--header", header,
      "--header-root", headerRoot,
      "--metadata", metadata,
      "--output-dir", outputDir,
      "--model", model,
    ],
    repoRoot,
  );

  const protoFile = path.join(outputDir, "flang_ast.proto");
  const generatedHeader = path.join(outputDir, "flang_ast.pb.h");
  const generatedSource = path.join(outputDir, "flang_ast.pb.cc");
  if (!fs.existsSync(protoFile)) throw new Error(`Python generation completed without writing ${protoFile}`);
  fs.rmSync(generatedHeader, { force: true });
  fs.rmSync(generatedSource, { force: true });

  runChild(
    "protoc generation",
    protoc,
    [`--proto_path=${outputDir}`, `--cpp_out=${outputDir}`, protoFile],
    repoRoot,
  );
  if (!fs.existsSync(generatedHeader) || !fs.existsSync(generatedSource)) {
    throw new Error("protoc exited successfully without writing flang_ast.pb.h and flang_ast.pb.cc");
  }

  console.log(`[clava-driver] Complete: declaration model, generated schema/producer, and protoc C++ outputs are in ${outputDir}`);
}


await main();
