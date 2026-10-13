import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { pathToFileURL } from "node:url";

const headerPath = path.resolve(process.env.FLANG_GENERATOR_HEADER ?? "");
const headerRoot = path.resolve(process.env.FLANG_GENERATOR_HEADER_ROOT ?? "");
const modelPath = path.resolve(process.env.FLANG_GENERATOR_MODEL_OUT ?? "");
const queryModule = process.env.FLANG_GENERATOR_QUERY_MODULE;
const qualifiedPrefix = process.env.FLANG_GENERATOR_QUALIFIED_PREFIX;

if (!process.env.FLANG_GENERATOR_HEADER || !process.env.FLANG_GENERATOR_HEADER_ROOT || !process.env.FLANG_GENERATOR_MODEL_OUT || !queryModule) {
  throw new Error("Set FLANG_GENERATOR_HEADER, FLANG_GENERATOR_HEADER_ROOT, FLANG_GENERATOR_MODEL_OUT, and FLANG_GENERATOR_QUERY_MODULE");
}

const { default: Query } = await import(pathToFileURL(path.resolve(queryModule)).href);

function sourceLocation(jp) {
  const location = String(jp.location ?? "");
  const match = /:(\d+):(\d+)(?: \(macro\))?(?: -> .*?)?$/.exec(location);
  if (!match || !jp.filepath) {
    throw new Error(`Clava did not provide a usable source location for ${jp.qualifiedName ?? jp.name}: ${location}`);
  }

  const file = path.relative(headerRoot, path.resolve(jp.filepath)).split(path.sep).join("/");
  if (file.startsWith("../") || path.isAbsolute(file)) {
    throw new Error(`Declaration is outside the analyzed header root: ${jp.filepath}`);
  }

  return {
    file,
    line: Number(match[1]),
    column: Number(match[2]),
    end_line: Number(jp.endLine ?? match[1]),
    end_column: Number(jp.endColumn ?? match[2]),
  };
}

function normalizeType(type) {
  if (!type || !type.code) throw new Error("Clava returned a field without a type");
  if (type.keys.includes("decl")) {
    const declaration = type.decl;
    if (declaration?.qualifiedName) return String(declaration.qualifiedName);
  }
  if (type.keys.includes("namedType")) {
    const namedType = type.namedType;
    if (namedType?.keys.includes("decl")) {
      const declaration = namedType.decl;
      if (declaration?.qualifiedName) return String(declaration.qualifiedName);
    }
  }
  return String(type.code).trim().replace(/\s+/g, " ");
}

function isInRoot(file) {
  const relative = path.relative(headerRoot, file);
  return relative !== "" && !relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative);
}

function sourceHash(file) {
  const absolute = path.resolve(file);
  if (!isInRoot(absolute)) throw new Error(`Source file is outside the analyzed header root: ${file}`);
  const relative = path.relative(headerRoot, absolute).split(path.sep).join("/");
  const digest = crypto.createHash("sha256").update(fs.readFileSync(absolute)).digest("hex");
  return { file: relative, sha256: digest };
}

function matchesPrefix(qualifiedName) {
  return !qualifiedPrefix || qualifiedName === qualifiedPrefix || qualifiedName.startsWith(`${qualifiedPrefix}::`);
}

const targetHeader = path.resolve(headerPath);
const declarations = [];
const seen = new Set();
const sourceFiles = new Map();

function rememberLocation(location) {
  const absolute = path.resolve(headerRoot, location.file);
  const item = sourceHash(absolute);
  sourceFiles.set(item.file, item.sha256);
}

for (const record of Query.search("record")) {
  if (!record.isImplementation || path.resolve(record.filepath ?? "") !== targetHeader) continue;
  const qualifiedName = String(record.qualifiedName ?? "");
  if (!qualifiedName) throw new Error(`Record at ${record.location} has no qualified name`);
  if (!matchesPrefix(qualifiedName)) continue;
  if (seen.has(qualifiedName)) throw new Error(`Duplicate record declaration: ${qualifiedName}`);
  seen.add(qualifiedName);
  const location = sourceLocation(record);
  rememberLocation(location);
  const members = record.fields.map((field) => {
    const fieldLocation = sourceLocation(field);
    rememberLocation(fieldLocation);
    return {
      name: String(field.name),
      type: normalizeType(field.type),
      location: fieldLocation,
    };
  });
  declarations.push({
    kind: "record",
    qualified_name: qualifiedName,
    location,
    members,
  });
}

for (const enumDecl of Query.search("enumDecl")) {
  if (path.resolve(enumDecl.filepath ?? "") !== targetHeader) continue;
  const qualifiedName = String(enumDecl.qualifiedName ?? "");
  if (!qualifiedName) throw new Error(`Enum at ${enumDecl.location} has no qualified name`);
  if (!matchesPrefix(qualifiedName)) continue;
  if (seen.has(qualifiedName)) throw new Error(`Duplicate declaration: ${qualifiedName}`);
  seen.add(qualifiedName);
  const location = sourceLocation(enumDecl);
  rememberLocation(location);
  const constants = enumDecl.enumerators.map((enumerator) => {
    const constantLocation = sourceLocation(enumerator);
    rememberLocation(constantLocation);
    return {
      name: String(enumerator.name),
      source: String(enumerator.code ?? enumerator.name).trim(),
      location: constantLocation,
    };
  });
  declarations.push({
    kind: "enum",
    qualified_name: qualifiedName,
    location,
    constants,
  });
}

declarations.sort((left, right) => left.qualified_name < right.qualified_name ? -1 : left.qualified_name > right.qualified_name ? 1 : 0);
if (declarations.length === 0) throw new Error(`No record or enum declarations found in ${targetHeader}`);

const headerBytes = fs.readFileSync(targetHeader);
const headerSource = sourceHash(targetHeader);
sourceFiles.set(headerSource.file, headerSource.sha256);
const model = {
  format: "clava-declaration-inventory/v1",
  source_header: {
    file: path.relative(headerRoot, targetHeader).split(path.sep).join("/"),
    sha256: crypto.createHash("sha256").update(headerBytes).digest("hex"),
  },
  source_files: [...sourceFiles.entries()]
    .sort(([left], [right]) => left < right ? -1 : left > right ? 1 : 0)
    .map(([file, sha256]) => ({ file, sha256 })),
  declarations,
};

fs.mkdirSync(path.dirname(modelPath), { recursive: true });
fs.writeFileSync(modelPath, `${JSON.stringify(model, null, 2)}\n`, "utf8");
