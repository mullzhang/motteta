import { compile } from "json-schema-to-typescript";
import { mkdir, readFile, writeFile } from "node:fs/promises";

const schema = JSON.parse(await readFile(new URL("../schemas/native-request.schema.json", import.meta.url), "utf8"));
const content = await compile(schema, "NativeRequest", { bannerComment: "/* Generated from schemas/native-request.schema.json. Do not edit. */" });
const output = new URL("src/generated/native-request.d.ts", import.meta.url);
if (process.argv.includes("--check")) {
  if (await readFile(output, "utf8") !== content) throw new Error("Generated TypeScript is out of date: npm run schemas");
} else {
  await mkdir(new URL("src/generated/", import.meta.url), { recursive: true });
  await writeFile(output, content);
}
