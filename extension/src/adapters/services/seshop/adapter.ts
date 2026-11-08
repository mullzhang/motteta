import { isbn, text } from "../../helpers";
import type { AdapterHandler } from "../../types";

const handler: AdapterHandler = {
  productAt(url, settings) {
    const match = url.pathname.match(/^\/product\/detail\/(\d+)\/?$/);
    return match ? { scope: settings.scope, id: match[1] } : null;
  },
  extract(doc, url, product) {
    const root = doc.querySelector(".cx_container_contents > section");
    const heading = text(root?.querySelector(":scope > h1") ?? null);
    const cover = root?.querySelector("#book-image-gallery img")?.getAttribute("src");
    if (!heading || !cover) return null;
    try {
      const target = new URL(cover, url);
      if (target.hostname !== url.hostname || !target.pathname.startsWith(`/static/images/product/${product.id}/`)) return null;
    } catch { return null; }

    const fields = new Map(Array.from(root!.querySelectorAll("dl.dl-horizontal dt"))
      .map(field => [text(field), text(field.nextElementSibling)]));
    const number = isbn(fields.get("ISBN") ?? null);
    const bundle = /【紙[＋+]PDFセット】$/.test(heading);
    // The same product route also serves courses and other non-book merchandise.
    if (!number && !bundle) return null;
    const delivery = fields.get("納品形態") ?? "";
    const print = /宅配便にてお届け/.test(delivery);
    const digital = /ダウンロード/.test(delivery) || /【PDF版】$/.test(heading);
    const format = bundle || print === digital ? "unknown" : print ? "print" : "digital";
    const title = heading.replace(/【(?:PDF版|紙[＋+]PDFセット)】$/, "").trim();
    const authors = Array.from(root!.querySelectorAll('a[href^="/product/author/"]'))
      .map(author => text(author)).filter((author): author is string => author !== null);
    return { product, book: { title, authors, isbn: number, format,
      volume: title.match(/第?(\d+)巻/)?.[1] ?? null, edition: title.match(/第\s*\d+\s*版/)?.[0] ?? null } };
  },
};

export default handler;
