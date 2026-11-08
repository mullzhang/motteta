import { cp, mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runInNewContext } from "node:vm";
import { JSDOM } from "jsdom";
import { afterEach, expect, it, vi } from "vitest";
import { buildExtension } from "../build.mjs";
import { discoverAdapters, extensionRoot, generateAdapters } from "../generate-adapters.mjs";

const temporary = [];
afterEach(async () => { for (const directory of temporary.splice(0)) await rm(directory, { recursive: true, force: true }); });

async function workspace() {
  const root = await mkdtemp(join(tmpdir(), "motteta-adapters-"));
  temporary.push(root);
  await cp(join(extensionRoot, "src"), join(root, "src"), { recursive: true });
  await cp(join(extensionRoot, "manifest.base.json"), join(root, "manifest.base.json"));
  return root;
}

async function addService(root, directory, settings) {
  const path = join(root, "src/adapters/services", directory);
  await mkdir(path);
  await writeFile(join(path, "adapter.json"), JSON.stringify(settings));
  await writeFile(join(path, "adapter.ts"), `
import type { AdapterHandler } from "../../types";
const handler: AdapterHandler = {
  productAt(url, settings) {
    const match = url.pathname.match(/^\\/books\\/([\\w-]+)$/);
    return match ? { scope: settings.scope, id: match[1] } : null;
  },
  extract(doc, _url, product) {
    const title = doc.querySelector("#new-service-heading")?.textContent;
    return title ? { product, book: { title, format: "digital", isbn: "9780000000002" } } : null;
  }
};
export default handler;
`);
}

const settings = { id: "fictional-books", matches: ["https://books.example.invalid/books/*"], scope: "new-catalog", anchorSelector: "#new-service-heading" };

it("discovers a service folder and wires permissions, content display, and native lookup without edits to common code", async () => {
  const root = await workspace();
  const common = ["src/adapters/index.ts", "src/adapters/registry.ts", "src/content/controller.ts", "src/background/handler.ts", "manifest.base.json"];
  const before = await Promise.all(common.map(path => readFile(join(root, path), "utf8")));
  await addService(root, "new-service", settings);
  await buildExtension(root);
  expect(await Promise.all(common.map(path => readFile(join(root, path), "utf8")))).toEqual(before);
  const manifest = JSON.parse(await readFile(join(root, "dist/manifest.json"), "utf8"));
  const base = JSON.parse(before[4]);
  expect(manifest.key).toBe(base.key);
  expect(manifest.host_permissions).toContain("https://books.example.invalid/*");
  expect(manifest.content_scripts[0].matches).toContain(settings.matches[0]);

  const url = "https://books.example.invalid/books/book-9";
  const page = new JSDOM('<main><h2 id="new-service-heading">架空の新サービスの本</h2></main>', { url, runScripts: "outside-only" });
  let lookup;
  let contentListener;
  Object.defineProperty(page.window.crypto, "randomUUID", { value: () => "offline-request" });
  page.window.chrome = { runtime: {
    id: "our-extension",
    sendMessage: async message => { lookup = message; return { result: "matches", label: "架空の所持記録あり" }; },
    onMessage: { addListener(listener) { contentListener = listener; } },
  } };
  try {
    page.window.eval(await readFile(join(root, "dist/content.js"), "utf8"));
    await vi.waitFor(() => expect(page.window.document.querySelector("[data-motteta]")?.textContent).toContain("架空の所持記録あり"));
    expect(lookup.candidate.identifiers).toEqual([{ namespace: settings.id, scope: settings.scope, value: "book-9" }]);
    const badge = page.window.document.querySelector("[data-motteta]");
    expect(badge.previousElementSibling.id).toBe("new-service-heading");
    let candidate;
    contentListener({ type: "get-candidate" }, { id: "our-extension" }, value => { candidate = value; });
    expect(candidate.identifiers[0].namespace).toBe(settings.id);

    let listener;
    const requests = [];
    const chrome = { runtime: { id: "our-extension", onMessage: { addListener(value) { listener = value; } },
      async sendNativeMessage(host, request) {
        requests.push({ host, request });
        return { schema_version: 1, request_id: request.request_id, result: "matches", label: "架空の所持記録あり", matches: [{ record: { private: "history-detail" } }] };
      },
    } };
    runInNewContext(await readFile(join(root, "dist/background.js"), "utf8"), { chrome, URL, setTimeout, clearTimeout, crypto: { randomUUID: () => "popup-request" } });
    const sender = { id: "our-extension", frameId: 0, tab: { id: 7 }, url };
    const summary = await new Promise(resolve => listener(lookup, sender, resolve));
    expect(requests).toHaveLength(1);
    expect(requests[0].request.operation).toBe("check");
    expect(requests[0].request.candidate.identifiers[0].namespace).toBe(settings.id);
    expect(summary).toEqual({ requestId: "offline-request", result: "matches", label: "架空の所持記録あり" });
    expect(JSON.stringify(summary)).not.toContain("history-detail");
    const denied = await new Promise(resolve => listener(lookup, { ...sender, url: "https://unapproved.example.invalid/books/book-9" }, resolve));
    expect(denied.result).toBe("error");
    expect(requests).toHaveLength(1);
  } finally {
    page.window.close();
  }
});

it("fails checks for stale generated files after an adapter setting changes", async () => {
  const root = await workspace();
  await generateAdapters({ root });
  const path = join(root, "src/adapters/services/amazon/adapter.json");
  const current = JSON.parse(await readFile(path, "utf8"));
  current.anchorSelector = "#changed-heading";
  await writeFile(path, JSON.stringify(current));
  await expect(generateAdapters({ root, check: true })).rejects.toThrow("out of date");
});

it("rejects duplicate service IDs and invalid permission definitions during discovery", async () => {
  const root = await workspace();
  await addService(root, "duplicate", { ...settings, id: "amazon" });
  await expect(discoverAdapters(root)).rejects.toThrow("Duplicate adapter ID");
  await rm(join(root, "src/adapters/services/duplicate"), { recursive: true });
  await addService(root, "invalid", { ...settings, matches: ["https://*/*"] });
  await expect(discoverAdapters(root)).rejects.toThrow("Invalid HTTPS");
});
