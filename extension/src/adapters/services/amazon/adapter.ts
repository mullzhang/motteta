import { formatFromText, isbn, structuredBook, structuredDetails, text } from "../../helpers";
import type { AdapterHandler } from "../../types";

const handler: AdapterHandler = {
  productAt(url, settings) {
    const match = url.pathname.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})(?:\/|$)/i);
    return match ? { scope: settings.scope, id: match[1].toUpperCase() } : null;
  },
  extract(doc, url, product) {
    const structured = structuredBook(doc, url);
    const base = structured && structuredDetails(structured);
    const root = doc.querySelector("#dp, #ppd");
    if (!root && !base) return null;
    const title = text(root?.querySelector("#productTitle") ?? null) ?? base?.title;
    // Amazon inserts direction marks between ISBN labels and their values.
    const details = text(root?.querySelector("#detailBullets_feature_div, #productDetails_detailBullets_sections1") ?? null)?.replace(/[\u200e\u200f]/g, "");
    const match = details?.match(/ISBN(?:-1[03])?\s*[:：]?\s*([\dXx][\dXx -]{8,20})/);
    const number = isbn(match?.[1] ?? null) ?? base?.isbn ?? null;
    const selectedSwatch = root?.querySelector("[id^='media_format_'].a-button-selected");
    const selection = text(selectedSwatch
      ? selectedSwatch.querySelector(".swatch-title-text")
      : root?.querySelector("#tmmSwatches .a-button-selected, #tmmSwatches [aria-checked='true']") ?? null);
    const selectedFormat = selection ? (/kindle/i.test(selection) ? "digital" : formatFromText(selection)) : base?.format ?? "unknown";
    if (!title || (!number && selectedFormat === "unknown" && !base)) return null;
    const asin = selectedSwatch?.closest("li[data-asin]")?.getAttribute("data-asin") ?? root?.querySelector<HTMLInputElement>("input#ASIN")?.value;
    return {
      product: { ...product, id: asin && /^[A-Z0-9]{10}$/.test(asin) ? asin : product.id },
      book: { ...base, title, isbn: number, format: selectedFormat, volume: title.match(/第?(\d+)巻/)?.[1] ?? null },
    };
  },
};

export default handler;
