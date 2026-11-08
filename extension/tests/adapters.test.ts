// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { extractCandidate, productAt } from "../src/adapters";
import { isbn } from "../src/adapters/helpers";

function fixture(name: string): Document {
  return new DOMParser().parseFromString(readFileSync(`tests/fixtures/${name}.html`, "utf8"), "text/html");
}

describe("synthetic product pages (not captured or verified live pages)", () => {
  it("extracts the selected Amazon book and ignores recommendations", () => {
    const candidate = extractCandidate(fixture("amazon"), "https://www.amazon.co.jp/dp/B0TEST0001/")!;
    expect(candidate.isbn).toBe("9780000000002");
    expect(candidate.format).toBe("print");
    expect(candidate.volume).toBe("1");
    expect(candidate.identifiers?.[0].value).toBe("B0TEST0001");
  });
  it("follows a selected ebook and changed ASIN", () => {
    const doc = fixture("amazon");
    doc.querySelector(".a-button-selected")!.textContent = "Kindle版";
    (doc.querySelector("#ASIN") as HTMLInputElement).value = "B0TEST0002";
    const candidate = extractCandidate(doc, "https://www.amazon.co.jp/dp/B0TEST0001/")!;
    expect(candidate.format).toBe("digital");
    expect(candidate.identifiers?.[0].value).toBe("B0TEST0002");
  });
  it("identifies Rakuten Books and shop-scoped marketplace products", () => {
    expect(extractCandidate(fixture("rakuten-books"), "https://books.rakuten.co.jp/rb/10000001/")?.isbn).toBe("9780000000002");
    const candidate = extractCandidate(fixture("rakuten-market"), "https://item.rakuten.co.jp/example-shop/book-1/")!;
    expect(candidate.isbn).toBe("9780000000002");
    expect(candidate.identifiers?.[0].scope).toBe("item.rakuten.co.jp/example-shop");
  });
  it("does not identify carts, histories, lookalike hosts or unknown markup", () => {
    for (const url of ["https://www.amazon.co.jp/gp/your-account/order-history", "https://evil.amazon.co.jp/dp/B0TEST0001", "http://www.amazon.co.jp/dp/B0TEST0001", "https://item.rakuten.co.jp/shop/", "https://amazon.co.jp.evil.test/dp/B0TEST0001"]) expect(productAt(url)).toBeNull();
    expect(extractCandidate(new DOMParser().parseFromString("<h1>Unknown</h1>", "text/html"), "https://item.rakuten.co.jp/shop/book/")).toBeNull();
  });
  it("rejects invalid ISBN checksums", () => {
    expect(isbn("9780000000001")).toBeNull();
    expect(isbn("0-13-235088-2")).toBe("0132350882");
  });
});

describe("Amazon layout reproduced from a user-provided saved page", () => {
  it("reads the selected media format and ISBN labels containing bidirectional marks", () => {
    const candidate = extractCandidate(fixture("amazon-media-format"), "https://www.amazon.co.jp/dp/B0TEST0001/");
    expect(candidate).toMatchObject({ title: "架空の技術書", format: "print", isbn: "0000000000" });
  });

  it("reads the selected format even when ISBN metadata is absent", () => {
    const doc = fixture("amazon-media-format");
    doc.querySelector("#detailBullets_feature_div")!.remove();
    expect(extractCandidate(doc, "https://www.amazon.co.jp/dp/B0TEST0001/")).toMatchObject({ format: "print", isbn: null });
  });

  it("uses the selected swatch's ASIN when the URL and hidden input still show the previous format", () => {
    const doc = fixture("amazon-media-format");
    doc.querySelector("#media_format_1")!.classList.remove("a-button-selected");
    doc.querySelector("#media_format_0")!.classList.add("a-button-selected");
    const candidate = extractCandidate(doc, "https://www.amazon.co.jp/dp/B0TEST0001/");
    expect(candidate).toMatchObject({ format: "digital", identifiers: [{ namespace: "amazon", scope: "amazon.co.jp", value: "B0TEST0002" }] });
  });

  it("does not infer a selected format from an unselected option or a previous Kindle purchase banner", () => {
    const doc = fixture("amazon-media-format");
    doc.querySelector("#detailBullets_feature_div")!.remove();
    doc.querySelector("#media_format_1")!.classList.remove("a-button-selected");
    expect(extractCandidate(doc, "https://www.amazon.co.jp/dp/B0TEST0001/")).toBeNull();
  });
});

describe("Rakuten layouts reproduced from the reported product pages", () => {
  it("reads Rakuten Books' product details without mixing the logo, author list or other formats into the title", () => {
    const candidate = extractCandidate(fixture("rakuten-books-product"), "https://books.rakuten.co.jp/rb/10000001/?variantId=10000001");
    expect(candidate).toMatchObject({
      title: "架空の技術書 第1巻", authors: ["架空の著者", "架空の訳者"],
      isbn: "9780000000002", format: "print", volume: "1",
      identifiers: [{ namespace: "rakuten-books", scope: "books.rakuten.co.jp", value: "10000001" }],
    });
  });

  it("does not infer Rakuten Books' format from the link to an electronic edition", () => {
    const doc = fixture("rakuten-books-product");
    const row = Array.from(doc.querySelectorAll("li.productInfo")).find(row => row.textContent?.includes("発行形態"))!;
    row.remove();
    expect(extractCandidate(doc, "https://books.rakuten.co.jp/rb/10000001/")?.format).toBe("unknown");
  });

  it("reads the marketplace product's ISBN and clean title, retaining its shop identity", () => {
    expect(extractCandidate(fixture("rakuten-market-product"), "https://item.rakuten.co.jp/example-shop/book-1/")).toMatchObject({
      title: "架空の技術書 第1巻", authors: ["架空の著者", "架空の訳者"],
      isbn: "9780000000002", format: "print", volume: "1",
      identifiers: [{ namespace: "rakuten-market", scope: "item.rakuten.co.jp/example-shop", value: "book-1" }],
    });
  });

  it("rejects marketplace metadata for another product or shop", () => {
    for (const url of ["https://item.rakuten.co.jp/example-shop/other-book/", "https://item.rakuten.co.jp/other-shop/book-1/"]) {
      expect(extractCandidate(fixture("rakuten-market-product"), url)).toBeNull();
    }
  });

  it("does not borrow the ISBN from a recommended product", () => {
    const doc = fixture("rakuten-market-product");
    doc.querySelector('#item-name-area meta[itemprop="gtin13"]')!.remove();
    expect(extractCandidate(doc, "https://item.rakuten.co.jp/example-shop/book-1/")).toBeNull();
  });

  it("does not infer a marketplace format from an ISBN alone or another product's delivery", () => {
    const doc = fixture("rakuten-market-product");
    doc.querySelector('#pagebody [irc="DeliveryMethod"]')!.remove();
    expect(extractCandidate(doc, "https://item.rakuten.co.jp/example-shop/book-1/")).toMatchObject({ isbn: "9780000000002", format: "unknown" });
  });
});
