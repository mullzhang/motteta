// @vitest-environment jsdom
import { expect, it } from "vitest";
import { createAdapterRegistry } from "../src/adapters/registry";
import { compileMatchPattern } from "../src/adapters/match-pattern";
import type { ServiceAdapter } from "../src/adapters/types";

function service(id = "fictional-store"): ServiceAdapter {
  return {
    settings: { id, matches: ["https://store.example.invalid/books/*"], scope: "fictional-catalog", anchorSelector: "#book-heading" },
    handler: {
      productAt(url, settings) {
        const match = url.pathname.match(/^\/books\/([\w-]+)$/);
        return match ? { scope: settings.scope, id: match[1] } : null;
      },
      extract(doc, _url, product) {
        const title = doc.querySelector("#book-heading")?.textContent;
        return title ? { product, book: { title, format: "digital" } } : null;
      },
    },
  };
}

it("uses a new service's namespace, extraction and insertion point without service branches", () => {
  document.body.innerHTML = '<main><h2 id="book-heading">架空の電子書籍</h2></main>';
  const registry = createAdapterRegistry([service()]);
  const url = "https://store.example.invalid/books/book-9";
  expect(registry.productAt(url)).toEqual({ source: "fictional-store", scope: "fictional-catalog", id: "book-9" });
  expect(registry.extractCandidate(document, url)).toMatchObject({ title: "架空の電子書籍", format: "digital", identifiers: [{ namespace: "fictional-store", scope: "fictional-catalog", value: "book-9" }] });
  expect(registry.insertionAnchor(document, url)?.id).toBe("book-heading");
  expect(registry.productAt("https://unapproved.example.invalid/books/book-9")).toBeNull();
});

it("does not choose an adapter by file order when two claim the same product", () => {
  const registry = createAdapterRegistry([service(), service("second-store")]);
  expect(registry.productAt("https://store.example.invalid/books/book-9")).toBeNull();
  expect(registry.extractCandidate(document, "https://store.example.invalid/books/book-9")).toBeNull();
});

it("matches exact hosts, subdomains, query strings and ports without widening lookalike hosts", () => {
  const wildcard = compileMatchPattern("https://*.example.invalid/books/*?view=ebook*");
  expect(wildcard.matches(new URL("https://example.invalid/books/1?view=ebook#details"))).toBe(true);
  expect(wildcard.matches(new URL("https://shop.example.invalid/books/1?view=ebook"))).toBe(true);
  for (const url of ["https://notexample.invalid/books/1?view=ebook", "https://example.invalid.evil.test/books/1?view=ebook", "http://example.invalid/books/1?view=ebook", "https://example.invalid/books/1?view=print"]) expect(wildcard.matches(new URL(url))).toBe(false);
  const explicit = compileMatchPattern("https://example.invalid:8443/books/*");
  expect(explicit.matches(new URL("https://example.invalid:8443/books/1"))).toBe(true);
  expect(explicit.matches(new URL("https://example.invalid/books/1"))).toBe(false);
  expect(compileMatchPattern("https://example.invalid:443/*").matches(new URL("https://example.invalid/"))).toBe(true);
  expect(compileMatchPattern("https://example.invalid/*").matches(new URL("https://example.invalid:8443/"))).toBe(true);
});

it("rejects undeclared global, malformed and non-HTTPS match patterns", () => {
  for (const pattern of ["<all_urls>", "https://*/*", "http://store.example.invalid/*", "https://example.*/*", "https://.example.invalid/*", "https://example.invalid:70000/*", "https://example.invalid/*#fragment"]) expect(() => compileMatchPattern(pattern)).toThrow();
});
