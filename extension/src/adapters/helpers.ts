import type { Candidate } from "../generated/native-request";
import type { BookDetails, Extraction, ProductIdentity } from "./types";

export function text(node: Element | null): string | null {
  const value = node?.textContent?.replace(/\s+/g, " ").trim();
  return value ? value.slice(0, 2000) : null;
}

export function isbn(value: string | null): string | null {
  if (!value) return null;
  const clean = value.replace(/[\s-]/g, "").toUpperCase();
  if (/^\d{9}[\dX]$/.test(clean) && [...clean].reduce((sum, c, i) => sum + (10 - i) * (c === "X" ? 10 : Number(c)), 0) % 11 === 0) return clean;
  if (/^97[89]\d{10}$/.test(clean) && [...clean].reduce((sum, c, i) => sum + Number(c) * (i % 2 ? 3 : 1), 0) % 10 === 0) return clean;
  return null;
}

export function formatFromText(value: string): Candidate["format"] {
  if (/ebook|e-book|電子|epub|pdf/i.test(value)) return "digital";
  if (/printbook|paperback|hardcover|単行本|文庫|新書|ハードカバー|ペーパーバック/i.test(value)) return "print";
  return "unknown";
}

export function structuredBook(doc: Document, url: URL): Record<string, unknown> | null {
  const books: Record<string, unknown>[] = [];
  for (const script of doc.querySelectorAll('script[type="application/ld+json"]')) {
    let value: unknown;
    try { value = JSON.parse(script.textContent ?? ""); } catch { continue; }
    const queue: unknown[] = Array.isArray(value) ? [...value] : [value];
    for (let i = 0; i < queue.length && i < 100; i++) {
      const item = queue[i];
      if (!item || typeof item !== "object") continue;
      const data = item as Record<string, unknown>;
      if (Array.isArray(data["@graph"])) queue.push(...data["@graph"]);
      const types = Array.isArray(data["@type"]) ? data["@type"] : [data["@type"]];
      if (!types.includes("Book")) continue;
      const link = typeof data.url === "string" ? data.url : typeof data["@id"] === "string" ? data["@id"] as string : null;
      if (!link) continue;
      try {
        const target = new URL(link, url);
        if (target.origin !== url.origin || target.pathname.replace(/\/$/, "") !== url.pathname.replace(/\/$/, "")) continue;
      } catch { continue; }
      books.push(data);
    }
  }
  return books.length === 1 ? books[0] : null;
}

export function structuredDetails(data: Record<string, unknown>): BookDetails | null {
  const title = typeof data.name === "string" ? data.name.trim().slice(0, 2000) : null;
  if (!title) return null;
  const authorData = data.author;
  const authors = (Array.isArray(authorData) ? authorData : authorData ? [authorData] : [])
    .map(a => typeof a === "string" ? a : a && typeof a === "object" && typeof a.name === "string" ? a.name : null)
    .filter((a): a is string => Boolean(a)).map(a => a.slice(0, 2000));
  return {
    title, authors, isbn: isbn(typeof data.isbn === "string" ? data.isbn : null),
    format: formatFromText(typeof data.bookFormat === "string" ? data.bookFormat : ""),
    volume: title.match(/第?(\d+)巻/)?.[1] ?? null,
    edition: typeof data.bookEdition === "string" ? data.bookEdition : null,
    language: typeof data.inLanguage === "string" ? data.inLanguage : null,
  };
}

export function extractStructuredBook(doc: Document, url: URL, product: ProductIdentity): Extraction | null {
  const data = structuredBook(doc, url);
  const book = data && structuredDetails(data);
  return book ? { product, book } : null;
}
