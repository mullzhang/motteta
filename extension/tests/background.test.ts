import { afterEach, expect, it, vi } from "vitest";
import { allowedContentSender, handleMessage } from "../src/background/handler";

const sender: chrome.runtime.MessageSender = { id: "our-extension", frameId: 0, tab: { id: 7 } as chrome.tabs.Tab, url: "https://www.amazon.co.jp/dp/B0TEST0001" };
afterEach(() => vi.unstubAllGlobals());

it("rejects unapproved origins, frames, extension IDs and missing tabs", () => {
  expect(allowedContentSender(sender, "our-extension")).toBe(true);
  for (const patch of [{ id: "other" }, { frameId: 1 }, { tab: undefined }, { url: "https://evil.test/dp/B0TEST0001" }]) expect(allowedContentSender({ ...sender, ...patch }, "our-extension")).toBe(false);
});

it("sends read-only requests and returns no history details to content scripts", async () => {
  const sendNativeMessage = vi.fn().mockImplementation(async (_name, message) => ({ schema_version: 1, request_id: message.request_id, result: "matches", label: "所持記録あり", matches: [{ record: { order_id: "private-order" } }] }));
  vi.stubGlobal("chrome", { runtime: { id: "our-extension", sendNativeMessage } });
  const result = await handleMessage({ type: "check", requestId: "r1", candidate: { schema_version:1,format:"print",isbn:"9780000000002" } }, sender);
  expect(sendNativeMessage.mock.calls[0][1].operation).toBe("check");
  expect(result).toEqual({ requestId:"r1", result:"matches", label:"所持記録あり" });
  expect(JSON.stringify(result)).not.toContain("private-order");
  await expect(handleMessage({ type: "delete_database" }, sender)).rejects.toThrow("Unsupported");
});

const popupSender: chrome.runtime.MessageSender = { id: "our-extension", url: "chrome-extension://our-extension/popup.html" };

it("checks the connection from the popup independently of the active page", async () => {
  const sendNativeMessage = vi.fn().mockImplementation(async (_host, request) => ({ schema_version: 1, request_id: request.request_id, result: "ok", record_count: 2 }));
  const query = vi.fn().mockResolvedValue([{ id: 7, url: "https://unrelated.example.invalid/" }]);
  const sendMessage = vi.fn();
  vi.stubGlobal("chrome", { runtime: { id: "our-extension", getURL: () => popupSender.url, sendNativeMessage }, tabs: { query, sendMessage } });

  expect(await handleMessage({ type: "status" }, popupSender)).toMatchObject({ result: "ok", record_count: 2 });
  expect(sendNativeMessage.mock.calls[0][1]).toMatchObject({ operation: "status" });
  expect(query).not.toHaveBeenCalled();
  expect(await handleMessage({ type: "details" }, popupSender)).toMatchObject({ result: "unsupported_page" });
  expect(sendMessage).not.toHaveBeenCalled();
  expect(sendNativeMessage).toHaveBeenCalledTimes(1);

  for (const denied of [sender, { ...popupSender, id: "other" }, { ...popupSender, url: "chrome-extension://our-extension/other.html" }]) {
    await expect(handleMessage({ type: "status" }, denied)).rejects.toThrow("Sender not allowed");
  }
  expect(sendNativeMessage).toHaveBeenCalledTimes(1);
});

it("distinguishes an unavailable content script from unreadable product metadata", async () => {
  const sendNativeMessage = vi.fn();
  const sendMessage = vi.fn().mockRejectedValueOnce(new Error("Receiving end does not exist")).mockResolvedValueOnce(null);
  vi.stubGlobal("chrome", { runtime: { id: "our-extension", getURL: () => popupSender.url, sendNativeMessage }, tabs: {
    query: vi.fn().mockResolvedValue([{ id: 7, url: sender.url }]), sendMessage
  } });

  const unavailable = await handleMessage({ type: "details" }, popupSender);
  expect(unavailable).toMatchObject({ result: "error", error: { code: "page_unavailable", message: expect.stringContaining("Receiving end does not exist") } });
  expect(await handleMessage({ type: "details" }, popupSender)).toMatchObject({
    result: "unidentified", label: "確認できません",
    error: { code: "product_unidentified", message: expect.stringContaining("商品情報") },
  });
  expect(sendNativeMessage).not.toHaveBeenCalled();
});

it("preserves native transport errors in the popup without leaking them to content scripts", async () => {
  let listener!: (message: unknown, sender: chrome.runtime.MessageSender, respond: (value: unknown) => void) => unknown;
  vi.stubGlobal("chrome", { runtime: {
    id: "our-extension", getURL: () => popupSender.url,
    sendNativeMessage: vi.fn().mockRejectedValue(new Error("Native host has exited.")),
    onMessage: { addListener(value: typeof listener) { listener = value; } }
  } });
  vi.resetModules();
  await import("../src/background/index");

  const error = await new Promise(resolve => listener({ type: "status" }, popupSender, resolve));
  expect(error).toMatchObject({ result: "error", error: { message: "Native host has exited." } });
  const summary = await new Promise(resolve => listener({ type: "check", requestId: "r1", candidate: { schema_version: 1, format: "print", isbn: "9780000000002" } }, sender, resolve));
  expect(summary).toMatchObject({ result: "error" });
  expect(summary).not.toHaveProperty("error");
  expect(JSON.stringify(summary)).not.toContain("Native host has exited.");
});
