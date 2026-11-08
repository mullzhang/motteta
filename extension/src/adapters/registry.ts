import type { Candidate } from "../generated/native-request";
import { compileMatchPattern } from "./match-pattern";
import type { Product, ServiceAdapter } from "./types";

export function createAdapterRegistry(adapters: readonly ServiceAdapter[]) {
  const entries = adapters.map(adapter => ({ ...adapter, patterns: adapter.settings.matches.map(compileMatchPattern) }));

  function resolve(href: string) {
    let url: URL;
    try { url = new URL(href); } catch { return null; }
    const found = entries.flatMap(entry => {
      if (!entry.patterns.some(pattern => pattern.matches(url))) return [];
      const product = entry.handler.productAt(url, entry.settings);
      return product ? [{ ...entry, product, url }] : [];
    });
    // File ordering must not silently decide between conflicting adapters.
    return found.length === 1 ? found[0] : null;
  }

  return {
    productAt(href: string): Product | null {
      const entry = resolve(href);
      return entry ? { ...entry.product, source: entry.settings.id } : null;
    },
    extractCandidate(doc: Document, href: string): Candidate | null {
      const entry = resolve(href);
      if (!entry) return null;
      const extracted = entry.handler.extract(doc, entry.url, entry.product);
      if (!extracted) return null;
      return { ...extracted.book, schema_version: 1,
        identifiers: [{ namespace: entry.settings.id, scope: extracted.product.scope, value: extracted.product.id }],
        url: entry.url.origin + entry.url.pathname };
    },
    insertionAnchor(doc: Document, href: string): Element | null {
      const entry = resolve(href);
      return entry ? doc.querySelector(entry.settings.anchorSelector) : null;
    },
  };
}
