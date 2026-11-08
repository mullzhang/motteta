// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { PageController } from "../src/content/controller";

function page(): void {
  document.body.innerHTML = '<main id="dp"><h1 id="productTitle">架空の技術書</h1><div id="tmmSwatches"><span class="a-button-selected">単行本</span></div><input id="ASIN" value="B0TEST0001"></main>';
}

function replyLater() {
  let resolve!: (result: { result: string; label: string }) => void;
  const promise = new Promise<{ result: string; label: string }>(done => { resolve = done; });
  return { promise, resolve };
}
beforeEach(page);

it("ignores an old response after the selected edition changes", async () => {
  let oldResolve!: (value: { result: string; label: string }) => void;
  const send = vi.fn().mockImplementationOnce(() => new Promise(resolve => { oldResolve = resolve; }))
    .mockResolvedValueOnce({ result: "no_match", label: "記録なし" });
  const controller = new PageController(document, () => "https://www.amazon.co.jp/dp/B0TEST0001", send);
  const previous = controller.refresh();
  (document.querySelector("#ASIN") as HTMLInputElement).value = "B0TEST0002";
  document.querySelector(".a-button-selected")!.textContent = "Kindle版";
  await controller.refresh();
  oldResolve({ result: "matches", label: "OLD RESPONSE" });
  await previous;
  expect(document.querySelectorAll("[data-motteta]")).toHaveLength(1);
  expect(document.querySelector("[data-motteta]")!.textContent).toContain("記録なし");
  expect(document.body.textContent).not.toContain("OLD RESPONSE");
});

it("shows a connection failure rather than a missing purchase", async () => {
  const controller = new PageController(document, () => "https://www.amazon.co.jp/dp/B0TEST0001", vi.fn().mockRejectedValue(new Error("disconnected")));
  await controller.refresh();
  expect(document.querySelector("[data-motteta]")!.textContent).toContain("確認できません");
  expect(document.querySelector("[data-motteta]")!.textContent).not.toContain("記録なし");
});

it("restores the badge after a site redraws the same product", async () => {
  const send = vi.fn().mockResolvedValue({ result: "matches", label: "所持記録あり" });
  const controller = new PageController(document, () => "https://www.amazon.co.jp/dp/B0TEST0001", send);
  await controller.refresh();
  page();
  await controller.refresh();
  expect(document.querySelector("[data-motteta]")?.textContent).toContain("所持記録あり");
  expect(send).toHaveBeenCalledOnce();
});

it("updates supported and unsupported pages even when neither has extractable metadata", async () => {
  document.body.innerHTML = '<div id="productInfo"><h1>未特定の商品</h1></div>';
  let href = "https://books.rakuten.co.jp/";
  const send = vi.fn();
  const controller = new PageController(document, () => href, send);
  await controller.refresh();
  expect(document.querySelector("[data-motteta]")).toBeNull();
  href = "https://books.rakuten.co.jp/rb/10000001/";
  await controller.refresh();
  expect(document.querySelector("[data-motteta]")?.textContent).toContain("確認できません");
  href = "https://books.rakuten.co.jp/";
  await controller.refresh();
  expect(document.querySelector("[data-motteta]")).toBeNull();
  expect(send).not.toHaveBeenCalled();
});

it("places the Amazon result below the product heading rather than a hidden assistant heading", async () => {
  document.body.innerHTML = new DOMParser().parseFromString(readFileSync("tests/fixtures/amazon-media-format.html", "utf8"), "text/html").body.innerHTML;
  const send = vi.fn().mockResolvedValue({ result: "no_match", label: "記録なし" });
  const controller = new PageController(document, () => "https://www.amazon.co.jp/dp/B0TEST0001/", send);
  await controller.refresh();
  const badge = document.querySelector("[data-motteta]")!;
  expect(badge.previousElementSibling?.id).toBe("title");
  expect(badge.closest("[hidden]")).toBeNull();
  expect(badge.textContent).toContain("記録なし");
  expect(send).toHaveBeenCalledOnce();
});

it.each([
  ["rakuten-books-product", "https://books.rakuten.co.jp/rb/10000001/", "#productInfo h1"],
  ["rakuten-market-product", "https://item.rakuten.co.jp/example-shop/book-1/", "#item-name-area"],
])("places %s's badge at the product title instead of the header or page top", async (name, url, selector) => {
  document.body.innerHTML = new DOMParser().parseFromString(readFileSync(`tests/fixtures/${name}.html`, "utf8"), "text/html").body.innerHTML;
  const send = vi.fn().mockResolvedValue({ result: "matches", label: "記録あり" });
  await new PageController(document, () => url, send).refresh();
  const badge = document.querySelector("[data-motteta]")!;
  expect(badge.previousElementSibling).toBe(document.querySelector(selector));
  expect(badge.closest("header")).toBeNull();
  expect(document.body.firstElementChild).not.toBe(badge);
  expect(badge.textContent).toContain("記録あり");
  expect(send).toHaveBeenCalledOnce();
});

it("waits for the product anchor instead of inserting a temporary badge at the top", async () => {
  document.body.innerHTML = '<header><h1>書店ロゴ</h1></header><main></main>';
  const send = vi.fn().mockResolvedValue({ result: "matches", label: "所持記録あり" });
  const controller = new PageController(document, () => "https://books.rakuten.co.jp/rb/10000001/", send);
  await controller.refresh();
  expect(document.querySelector("[data-motteta]")).toBeNull();
  expect(send).not.toHaveBeenCalled();
  document.querySelector("main")!.innerHTML = new DOMParser().parseFromString(readFileSync("tests/fixtures/rakuten-books-product.html", "utf8"), "text/html").querySelector("#main")!.innerHTML;
  await controller.refresh();
  expect(document.querySelector("[data-motteta]")?.previousElementSibling).toBe(document.querySelector("#productInfo h1"));
  expect(send).toHaveBeenCalledOnce();
});

it("shows only the final result and coalesces refreshes while the first lookup is pending", async () => {
  const reply = replyLater();
  const send = vi.fn().mockReturnValue(reply.promise);
  const controller = new PageController(document, () => "https://www.amazon.co.jp/dp/B0TEST0001/", send);
  const pending = controller.refresh();
  await controller.refresh();
  await controller.refresh(true);
  expect(send).toHaveBeenCalledOnce();
  expect(document.querySelector("[data-motteta]")).toBeNull();
  expect(document.body.textContent).not.toContain("確認中");
  reply.resolve({ result: "matches", label: "同じ本の可能性あり" });
  await pending;
  expect(document.querySelector("[data-motteta]")?.textContent).toBe("Motteta：同じ本の可能性あり");
});

it("preserves the existing badge during a forced lookup and does not rewrite an unchanged result", async () => {
  const reply = replyLater();
  const send = vi.fn().mockResolvedValueOnce({ result: "matches", label: "同じ本の可能性あり" }).mockReturnValueOnce(reply.promise);
  const controller = new PageController(document, () => "https://www.amazon.co.jp/dp/B0TEST0001/", send);
  await controller.refresh();
  const badge = document.querySelector("[data-motteta]")!;
  const changed = vi.fn();
  const observer = new MutationObserver(changed);
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  try {
    const pending = controller.refresh(true);
    expect(document.querySelector("[data-motteta]")).toBe(badge);
    expect(badge.textContent).toBe("Motteta：同じ本の可能性あり");
    reply.resolve({ result: "matches", label: "同じ本の可能性あり" });
    await pending;
    await Promise.resolve();
    expect(document.querySelector("[data-motteta]")).toBe(badge);
    expect(changed).not.toHaveBeenCalled();
  } finally { observer.disconnect(); }
});

it("keeps the result while metadata is enriched for the same product", async () => {
  const reply = replyLater();
  const send = vi.fn().mockResolvedValueOnce({ result: "matches", label: "同じ本の可能性あり" }).mockReturnValueOnce(reply.promise);
  const controller = new PageController(document, () => "https://www.amazon.co.jp/dp/B0TEST0001/", send);
  await controller.refresh();
  const badge = document.querySelector("[data-motteta]")!;
  const details = document.createElement("div");
  details.id = "detailBullets_feature_div";
  details.textContent = "ISBN-13：9780000000002";
  document.querySelector("main")!.append(details);
  const pending = controller.refresh();
  expect(document.querySelector("[data-motteta]")).toBe(badge);
  expect(badge.textContent).toBe("Motteta：同じ本の可能性あり");
  reply.resolve({ result: "matches", label: "記録あり" });
  await pending;
  expect(document.querySelector("[data-motteta]")).toBe(badge);
  expect(badge.textContent).toBe("Motteta：記録あり");
});

it("keeps the result when an unknown format becomes known for the same product", async () => {
  const swatch = document.querySelector(".a-button-selected")!;
  swatch.classList.remove("a-button-selected");
  const details = document.createElement("div");
  details.id = "detailBullets_feature_div";
  details.textContent = "ISBN-13：9780000000002";
  document.querySelector("main")!.append(details);
  const reply = replyLater();
  const send = vi.fn().mockResolvedValueOnce({ result: "matches", label: "同じ本の可能性あり" }).mockReturnValueOnce(reply.promise);
  const controller = new PageController(document, () => "https://www.amazon.co.jp/dp/B0TEST0001/", send);
  await controller.refresh();
  const badge = document.querySelector("[data-motteta]")!;
  swatch.classList.add("a-button-selected");
  const pending = controller.refresh();
  expect(document.querySelector("[data-motteta]")).toBe(badge);
  expect(badge.textContent).toBe("Motteta：同じ本の可能性あり");
  reply.resolve({ result: "matches", label: "記録あり" });
  await pending;
  expect(document.querySelector("[data-motteta]")).toBe(badge);
  expect(badge.textContent).toBe("Motteta：記録あり");
});

it("clears a known different format even before the product ID changes", async () => {
  const reply = replyLater();
  const send = vi.fn().mockResolvedValueOnce({ result: "matches", label: "記録あり" }).mockReturnValueOnce(reply.promise);
  const controller = new PageController(document, () => "https://www.amazon.co.jp/dp/B0TEST0001/", send);
  await controller.refresh();
  document.querySelector(".a-button-selected")!.textContent = "Kindle版";
  const pending = controller.refresh();
  expect(document.querySelector("[data-motteta]")).toBeNull();
  reply.resolve({ result: "matches", label: "同じ本の可能性あり" });
  await pending;
  expect(document.querySelector("[data-motteta]")?.textContent).toBe("Motteta：同じ本の可能性あり");
});

it("removes the old result immediately when the selected product changes", async () => {
  const reply = replyLater();
  const send = vi.fn().mockResolvedValueOnce({ result: "matches", label: "記録あり" }).mockReturnValueOnce(reply.promise);
  const controller = new PageController(document, () => "https://www.amazon.co.jp/dp/B0TEST0001/", send);
  await controller.refresh();
  (document.querySelector("#ASIN") as HTMLInputElement).value = "B0TEST0002";
  document.querySelector(".a-button-selected")!.textContent = "Kindle版";
  const pending = controller.refresh();
  expect(document.querySelector("[data-motteta]")).toBeNull();
  reply.resolve({ result: "no_match", label: "記録なし" });
  await pending;
  expect(document.querySelector("[data-motteta]")?.textContent).toBe("Motteta：記録なし");
});

it("restores the same badge after a redraw without duplicating an in-flight lookup", async () => {
  const reply = replyLater();
  const send = vi.fn().mockResolvedValueOnce({ result: "matches", label: "記録あり" }).mockReturnValueOnce(reply.promise);
  const controller = new PageController(document, () => "https://www.amazon.co.jp/dp/B0TEST0001/", send);
  await controller.refresh();
  const badge = document.querySelector("[data-motteta]")!;
  const pending = controller.refresh(true);
  page();
  await controller.refresh();
  expect(document.querySelector("[data-motteta]")).toBe(badge);
  expect(badge.textContent).toBe("Motteta：記録あり");
  expect(send).toHaveBeenCalledTimes(2);
  reply.resolve({ result: "matches", label: "記録あり" });
  await pending;
});

it("does not attach an old response when the product changes before the observer refreshes", async () => {
  const reply = replyLater();
  const send = vi.fn().mockReturnValueOnce(reply.promise).mockResolvedValueOnce({ result: "no_match", label: "記録なし" });
  const controller = new PageController(document, () => "https://www.amazon.co.jp/dp/B0TEST0001/", send);
  const pending = controller.refresh();
  (document.querySelector("#ASIN") as HTMLInputElement).value = "B0TEST0002";
  document.querySelector(".a-button-selected")!.textContent = "Kindle版";
  reply.resolve({ result: "matches", label: "OLD RESPONSE" });
  await pending;
  expect(document.body.textContent).not.toContain("OLD RESPONSE");
  expect(document.querySelector("[data-motteta]")?.textContent).toBe("Motteta：記録なし");
  expect(send).toHaveBeenCalledTimes(2);
});

it("replaces the retained result with an error when the refresh fails", async () => {
  const send = vi.fn().mockResolvedValueOnce({ result: "matches", label: "記録あり" }).mockRejectedValueOnce(new Error("disconnected"));
  const controller = new PageController(document, () => "https://www.amazon.co.jp/dp/B0TEST0001/", send);
  await controller.refresh();
  const badge = document.querySelector("[data-motteta]")!;
  await controller.refresh(true);
  expect(document.querySelector("[data-motteta]")).toBe(badge);
  expect(badge.textContent).toBe("Motteta：確認できません");
});
