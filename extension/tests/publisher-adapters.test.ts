// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { extractCandidate, productAt } from "../src/adapters";

function fixture(name: string): Document {
  return new DOMParser().parseFromString(readFileSync(`tests/fixtures/${name}-product.html`, "utf8"), "text/html");
}

const oreillyUrl = "https://www.oreilly.co.jp/books/9780000000002/";
const gihyoUrl = "https://gihyo.jp/dp/ebook/2026/978-0-000-00000-2";
const seshopUrl = "https://www.seshop.com/product/detail/10001";

describe("publisher layouts reproduced from public product pages with fictional metadata", () => {
  it("keeps O'Reilly's mixed print and ebook page ambiguous", () => {
    expect(extractCandidate(fixture("oreilly-japan"), oreillyUrl)).toMatchObject({
      title: "架空のデータ設計 第2版", authors: ["架空 著者", "架空 訳者"],
      isbn: "9780000000002", format: "unknown", edition: "第2版",
      identifiers: [{ namespace: "oreilly-japan", scope: "oreilly.co.jp", value: "9780000000002" }],
    });
  });

  it.each([["Print", "print"], ["PDF EPUB", "digital"], ["", "unknown"]])(
    "reads O'Reilly's format list %s without borrowing purchase-link text", (formats, expected) => {
      const doc = fixture("oreilly-japan");
      const field = doc.querySelector(".buying-options")!.parentElement!;
      for (const node of Array.from(field.childNodes)) if (node.nodeType === 3) node.textContent = formats;
      expect(extractCandidate(doc, oreillyUrl)?.format).toBe(expected);
    },
  );

  it("does not use O'Reilly's stale product metadata or recommendation ISBN", () => {
    expect(extractCandidate(fixture("oreilly-japan"), "https://www.oreilly.co.jp/books/9780000000019/")).toBeNull();
    const doc = fixture("oreilly-japan");
    doc.querySelector('.item-props [itemprop="isbn"]')!.remove();
    expect(extractCandidate(doc, oreillyUrl)).toBeNull();
  });

  it("reads GDP's electronic edition ISBN from its own URL rather than the paper link", () => {
    expect(extractCandidate(fixture("gihyo-dp"), gihyoUrl)).toMatchObject({
      title: "架空のバックエンド開発 第2版", authors: ["架空 著者"],
      isbn: "9780000000002", format: "digital", edition: "第2版",
      identifiers: [{ namespace: "gihyo-dp", scope: "gihyo.jp/dp", value: "9780000000002" }],
    });
  });

  it.each([null, "invalid", "https://gihyo.jp/dp/ebook/2026/978-0-000-00001-9", "https://unrelated.example.invalid/dp/ebook/2026/978-0-000-00000-2"])(
    "rejects missing or mismatched GDP page identity %s", canonical => {
      const doc = fixture("gihyo-dp");
      const meta = doc.querySelector('meta[property="og:url"]')!;
      if (canonical === null) meta.remove(); else meta.setAttribute("content", canonical);
      expect(extractCandidate(doc, gihyoUrl)).toBeNull();
    },
  );

  it("accepts GDP's equivalent trailing slash and URL query without changing its identifier", () => {
    const candidate = extractCandidate(fixture("gihyo-dp"), `${gihyoUrl}/?utm_source=test`)!;
    expect(candidate.identifiers?.[0].value).toBe("9780000000002");
    expect(candidate.url).toBe(`${gihyoUrl}/`);
  });

  it("reads SEshop's paper edition, scoped authors, and URL product ID", () => {
    expect(extractCandidate(fixture("seshop"), seshopUrl)).toMatchObject({
      title: "架空のWeb API入門 第1巻", authors: ["架空 著者", "架空 訳者"],
      isbn: "9780000000002", format: "print", volume: "1",
      identifiers: [{ namespace: "seshop", scope: "seshop.com", value: "10001" }],
    });
  });

  it("reads SEshop's PDF edition without including the format marker in its book title", () => {
    const doc = fixture("seshop");
    doc.querySelector("section > h1")!.textContent += "【PDF版】";
    doc.querySelector("dl dt:nth-of-type(2)")!.nextElementSibling!.textContent = "会員メニューよりダウンロード";
    expect(extractCandidate(doc, seshopUrl)).toMatchObject({ title: "架空のWeb API入門 第1巻", format: "digital" });
  });

  it("keeps SEshop's paper-plus-PDF bundle ambiguous even though delivery is postal", () => {
    const doc = fixture("seshop");
    doc.querySelector("section > h1")!.textContent += "【紙＋PDFセット】";
    doc.querySelector("dl dt:nth-of-type(3)")!.nextElementSibling!.remove();
    doc.querySelector("dl dt:nth-of-type(3)")!.remove();
    expect(extractCandidate(doc, seshopUrl)).toMatchObject({ title: "架空のWeb API入門 第1巻", isbn: null, format: "unknown" });
  });

  it("does not guess SEshop's format from other-format links or an ISBN alone", () => {
    const doc = fixture("seshop");
    doc.querySelector("dl dt:nth-of-type(2)")!.nextElementSibling!.textContent = "不明";
    expect(extractCandidate(doc, seshopUrl)?.format).toBe("unknown");
  });

  it("rejects SEshop's stale product, foreign cover and non-book metadata", () => {
    expect(extractCandidate(fixture("seshop"), "https://www.seshop.com/product/detail/10002")).toBeNull();
    const foreign = fixture("seshop");
    foreign.querySelector("#book-image-gallery img")!.setAttribute("src", "https://unrelated.example.invalid/static/images/product/10001/L.png");
    expect(extractCandidate(foreign, seshopUrl)).toBeNull();
    const nonBook = fixture("seshop");
    nonBook.querySelector("section h1")!.textContent = "架空の研修講座";
    nonBook.querySelector("dl dt:nth-of-type(3)")!.nextElementSibling!.textContent = "なし";
    expect(extractCandidate(nonBook, seshopUrl)).toBeNull();
  });

  it.each([
    "https://www.oreilly.co.jp/books/", "https://www.oreilly.co.jp/books/database/",
    "https://www.oreilly.co.jp/books/9780000000001/", "https://www.oreilly.co.jp/ebook/cart?id=9780000000002",
    "https://gihyo.jp/dp/", "https://gihyo.jp/book/2026/978-0-000-00000-2",
    "https://gihyo.jp/dp/ebook/2026/978-0-000-00000-1", "https://gihyo.jp/dp/ebook/2026/978-0-000-00000-2/checkout",
    "https://www.seshop.com/product/author/10001", "https://www.seshop.com/product/detail/10001/checkout",
    "http://www.seshop.com/product/detail/10001", "https://www.oreilly.co.jp.evil.test/books/9780000000002/",
    "https://evil.gihyo.jp/dp/ebook/2026/978-0-000-00000-2", "https://www.seshop.com.evil.test/product/detail/10001",
  ])("does not support catalogs, carts, other routes or lookalike hosts: %s", url => {
    expect(productAt(url)).toBeNull();
  });
});
