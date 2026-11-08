// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const html = readFileSync("src/popup/popup.html", "utf8");
beforeEach(() => {
  vi.resetModules();
  document.open(); document.write(html); document.close();
});
afterEach(() => vi.unstubAllGlobals());

it("shows a working connection even when the active tab is not a product page", async () => {
  vi.stubGlobal("chrome", { runtime: { sendMessage: vi.fn(async message => message.type === "status"
    ? { schema_version: 1, result: "ok" }
    : { schema_version: 1, result: "unsupported_page", label: "対応サイトの商品ページを開いてください。" }) } });
  await import("../src/popup/index");

  await vi.waitFor(() => expect(document.querySelector("#connection")?.textContent).toBe("ローカル台帳：接続済み"));
  expect(document.querySelector("#status")?.textContent).toContain("商品ページを開いてください");
  expect(document.querySelector("#error")?.textContent).toBe("");
  expect(document.querySelector("#freshness")?.textContent).toBe("");
});

it("shows the native connection error separately from page guidance", async () => {
  vi.stubGlobal("chrome", { runtime: { sendMessage: vi.fn(async message => message.type === "status"
    ? { schema_version: 1, result: "error", error: { code: "extension_error", message: "Specified native messaging host not found." } }
    : { schema_version: 1, result: "unsupported_page", label: "対応サイトの商品ページを開いてください。" }) } });
  await import("../src/popup/index");

  await vi.waitFor(() => expect(document.querySelector("#connection")?.textContent).toBe("ローカル台帳：接続できません"));
  expect(document.querySelector("#connection-error")?.textContent).toContain("native messaging host not found");
  expect(document.querySelector("#status")?.textContent).toContain("商品ページを開いてください");
  expect(document.body.textContent).not.toContain("記録なし");
});

it("keeps a page communication failure separate from a healthy native connection", async () => {
  vi.stubGlobal("chrome", { runtime: { sendMessage: vi.fn(async message => message.type === "status"
    ? { schema_version: 1, result: "ok" }
    : { schema_version: 1, result: "error", error: { code: "page_unavailable", message: "商品ページを再読み込みしてください。" } }) } });
  await import("../src/popup/index");

  await vi.waitFor(() => expect(document.querySelector("#error")?.textContent).toContain("再読み込み"));
  expect(document.querySelector("#connection")?.textContent).toBe("ローカル台帳：接続済み");
  expect(document.querySelector("#connection-error")?.textContent).toBe("");
});

it("keeps an unidentified product's explanation below the simple status", async () => {
  vi.stubGlobal("chrome", { runtime: { sendMessage: vi.fn(async message => message.type === "status"
    ? { schema_version: 1, result: "ok" }
    : { schema_version: 1, result: "unidentified", label: "確認できません",
      error: { code: "product_unidentified", message: "商品情報を読み取れません。商品詳細ページを再読み込みしてください。" } }) } });
  await import("../src/popup/index");
  await vi.waitFor(() => expect(document.querySelector("#status")?.textContent).toBe("確認できません"));
  expect(document.querySelector("#connection")?.textContent).toBe("ローカル台帳：接続済み");
  expect(document.querySelector("#error")?.textContent).toContain("商品情報を読み取れません");
  expect(document.querySelector("#records")?.textContent).toBe("");
  expect(document.body.textContent).not.toContain("記録なし");
});
