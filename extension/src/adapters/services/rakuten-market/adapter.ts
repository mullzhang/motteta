import { extractStructuredBook, isbn, text } from "../../helpers";
import type { AdapterHandler } from "../../types";

const handler: AdapterHandler = {
  productAt(url, settings) {
    const match = url.pathname.match(/^\/([^/]+)\/([^/]+)\/?$/);
    return match ? { scope: `${settings.scope}/${match[1]}`, id: match[2] } : null;
  },
  extract(doc, url, product) {
    const structured = extractStructuredBook(doc, url, product);
    if (structured) return structured;

    const root = doc.querySelector('#pagebody[itemscope][itemtype$="/Product"]');
    const heading = root?.querySelector("#item-name-area");
    const sku = heading?.querySelector('meta[itemprop="sku"]')?.getAttribute("content");
    if (!root || !heading || sku !== `${url.pathname.split("/")[1]}:${product.id}`) return null;
    const number = isbn(heading.querySelector('meta[itemprop="gtin13"]')?.getAttribute("content") ?? null);
    const fields = new Map(Array.from(root.querySelectorAll('[irc="SpecTableArea"] tr'))
      .map(row => [text(row.children[0] ?? null), text(row.children[1] ?? null)]));
    const title = fields.get("タイトル");
    if (!title || !number) return null;
    const authorRow = Array.from(root.querySelectorAll(".item_desc .boox_item tr"))
      .find(row => text(row.children[0] ?? null) === "著者");
    const authors = Array.from(authorRow?.children[1]?.querySelectorAll("a") ?? [])
      .map(author => text(author)).filter((author): author is string => author !== null);
    // A valid book ISBN and the current product's postal delivery identify a physical book.
    // ISBN alone does not establish its format.
    const delivery = text(root.querySelector('[irc="DeliveryMethod"]'));
    const format = delivery && /メール便|日本郵便/.test(delivery) ? "print" : "unknown";
    return { product, book: { title, authors, isbn: number, format, volume: title.match(/第?(\d+)巻/)?.[1] ?? null } };
  },
};

export default handler;
