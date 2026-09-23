import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { pathToFileURL } from "node:url";

const headerPath = path.resolve(process.env.FLANG_GENERATOR_HEADER ?? "");
const headerRoot = path.resolve(process.env.FLANG_GENERATOR_HEADER_ROOT ?? "");
const modelPath = path.resolve(process.env.FLANG_GENERATOR_MODEL_OUT ?? "");
const queryModule = process.env.FLANG_GENERATOR_QUERY_MODULE;

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

const targetHeader = path.resolve(headerPath);
const declarations = [];
const seen = new Set();

for (const record of Query.search("record")) {
  if (!record.isImplementation || path.resolve(record.filepath ?? "") !== targetHeader) continue;
  const qualifiedName = String(record.qualifiedName ?? "");
  if (!qualifiedName) throw new Error(`Record at ${record.location} has no qualified name`);
  if (seen.has(qualifiedName)) throw new Error(`Duplicate record declaration: ${qualifiedName}`);
  seen.add(qualifiedName);
  declarations.push({
    kind: "record",
    qualified_name: qualifiedName,
    location: sourceLocation(record),
    members: record.fields.map((field) => ({
      name: String(field.name),
      type: normalizeType(field.type),
      location: sourceLocation(field),
    })),
  });
}

for (const enumDecl of Query.search("enumDecl")) {
  if (path.resolve(enumDecl.filepath ?? "") !== targetHeader) continue;
  const qualifiedName = String(enumDecl.qualifiedName ?? "");
  if (!qualifiedName) throw new Error(`Enum at ${enumDecl.location} has no qualified name`);
  if (seen.has(qualifiedName)) throw new Error(`Duplicate declaration: ${qualifiedName}`);
  seen.add(qualifiedName);
  declarations.push({
    kind: "enum",
    qualified_name: qualifiedName,
    location: sourceLocation(enumDecl),
    constants: enumDecl.enumerators.map((enumerator) => ({
      name: String(enumerator.name),
      source: String(enumerator.code ?? enumerator.name).trim(),
      location: sourceLocation(enumerator),
    })),
  });
}

declarations.sort((left, right) => left.qualified_name < right.qualified_name ? -1 : left.qualified_name > right.qualified_name ? 1 : 0);
if (declarations.length === 0) throw new Error(`No record or enum declarations found in ${targetHeader}`);

const headerBytes = fs.readFileSync(targetHeader);
const model = {
  format: "clava-declaration-inventory/v1",
  source_header: {
    file: path.relative(headerRoot, targetHeader).split(path.sep).join("/"),
    sha256: crypto.createHash("sha256").update(headerBytes).digest("hex"),
  },
  declarations,
};

fs.mkdirSync(path.dirname(modelPath), { recursive: true });
fs.writeFileSync(modelPath, `${JSON.stringify(model, null, 2)}\n`, "utf8");
