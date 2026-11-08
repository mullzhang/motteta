import { isbn, text } from "../../helpers";
import type { AdapterHandler } from "../../types";

const handler: AdapterHandler = {
  productAt(url, settings) {
    const match = url.pathname.match(/^\/dp\/ebook\/\d{4}\/([\d-]+)\/?$/);
    const id = isbn(match?.[1] ?? null);
    return id ? { scope: settings.scope, id } : null;
  },
  extract(doc, url, product) {
    const root = doc.querySelector("#bookInforMain");
    const title = text(root?.querySelector("#bookTitle") ?? null);
    const canonical = doc.querySelector('meta[property="og:url"]')?.getAttribute("content");
    if (!title || !canonical) return null;
    try {
      const target = new URL(canonical, url);
      if (target.origin !== url.origin || target.pathname.replace(/\/$/, "") !== url.pathname.replace(/\/$/, "")) return null;
    } catch { return null; }

    const authors = Array.from(root!.querySelectorAll('[itemprop="author"]'))
      .flatMap(author => (text(author) ?? "").split(/[、，,]/))
      .map(name => name.replace(/\s*(?:編著|監訳|監修|著|訳|編)\s*$/, "").trim()).filter(Boolean);
    // The ebook URL identifies this electronic edition, not the linked paper edition.
    return { product, book: { title, authors, isbn: product.id, format: "digital",
      volume: title.match(/第?(\d+)巻/)?.[1] ?? null, edition: title.match(/第\s*\d+\s*版/)?.[0] ?? null } };
  },
};

export default handler;
