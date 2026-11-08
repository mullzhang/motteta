import { extractStructuredBook, formatFromText, isbn, text } from "../../helpers";
import type { AdapterHandler } from "../../types";

const handler: AdapterHandler = {
  productAt(url, settings) {
    const match = url.pathname.match(/^\/rb\/(\d+)(?:\/|$)/);
    return match ? { scope: settings.scope, id: match[1] } : null;
  },
  extract(doc, url, product) {
    const structured = extractStructuredBook(doc, url, product);
    if (structured) return structured;

    const heading = doc.querySelector("#productInfo h1");
    if (!heading) return null;
    const titleNode = heading.cloneNode(true) as Element;
    titleNode.querySelector(".authorLink")?.remove();
    const title = text(titleNode);
    const fields = new Map(Array.from(doc.querySelectorAll("#productDetailedDescription li.productInfo"))
      .map(row => [text(row.querySelector(".category")), row.querySelector(".categoryValue")]));
    const number = isbn(text(fields.get("ISBN") ?? null));
    const format = formatFromText(text(fields.get("発行形態") ?? null) ?? "");
    if (!title || (!number && format === "unknown")) return null;
    const authors = Array.from(fields.get("著者／編集")?.querySelectorAll("a") ?? [])
      .map(author => text(author)).filter((author): author is string => author !== null);
    return { product, book: { title, authors, isbn: number, format, volume: title.match(/第?(\d+)巻/)?.[1] ?? null } };
  },
};

export default handler;
