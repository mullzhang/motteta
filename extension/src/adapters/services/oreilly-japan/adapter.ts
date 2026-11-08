import { isbn, text } from "../../helpers";
import type { AdapterHandler } from "../../types";

const handler: AdapterHandler = {
  productAt(url, settings) {
    const match = url.pathname.match(/^\/books\/(\d{13})\/?$/);
    return match && isbn(match[1]) ? { scope: settings.scope, id: match[1] } : null;
  },
  extract(doc, _url, product) {
    const heading = doc.querySelector("#maincontent .pageWidth h1[itemprop='name']");
    const root = heading?.parentElement;
    const title = text(heading);
    const number = isbn(text(root?.querySelector('.item-props [itemprop="isbn"]') ?? null));
    if (!title || number !== product.id) return null;

    const formatField = Array.from(root!.querySelectorAll(".item-props dt"))
      .find(field => text(field) === "FORMAT")?.nextElementSibling;
    // Only the format list belongs here; purchase links also mention other formats.
    const formats = Array.from(formatField?.childNodes ?? [])
      .filter(node => node.nodeType === 3).map(node => node.textContent).join(" ");
    const print = /\bPrint\b/i.test(formats);
    const digital = /\b(?:PDF|EPUB|MOBI|Ebook)\b/i.test(formats);
    const format = print === digital ? "unknown" : print ? "print" : "digital";
    const authors = (text(root!.querySelector('[itemprop="author"]')) ?? "")
      .split(/[、，,]/).map(name => name.replace(/\s*(?:編著|監訳|監修|著|訳|編)\s*$/, "").trim()).filter(Boolean);
    return { product, book: { title, authors, isbn: number, format,
      volume: title.match(/第?(\d+)巻/)?.[1] ?? null, edition: title.match(/第\s*\d+\s*版/)?.[0] ?? null } };
  },
};

export default handler;
