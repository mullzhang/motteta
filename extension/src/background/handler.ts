import { productAt } from "../adapters";
import type { Candidate, NativeRequest } from "../generated/native-request";

export const HOST = "com.motteta.host";

export type HostResponse = {
  schema_version: number;
  request_id?: string;
  result: string;
  label?: string;
  matches?: { kind: string; reason: string; record: {
    id: string; book: { title: string; format: string; edition: string | null; volume: string | null };
    source: { name: string } | null; acquired_on: string | null; quantity: number;
    order_state: string | null; possession_state: string;
  } }[];
  freshness?: { sources: { source: { name: string }; account: string; last_complete: string | null;
    last_attempt: { observed_at: string; coverage: { status: string; unverified: string[]; checked_start: string | null; checked_end: string | null } } | null;
    confirmed_ranges: { requested_start: string; requested_end: string }[];
  }[]; unresolved_reviews: number };
  error?: { code: string; message: string };
};

export function allowedContentSender(sender: chrome.runtime.MessageSender, extensionId: string): boolean {
  return sender.id === extensionId && sender.frameId === 0 && sender.tab?.id !== undefined &&
    typeof sender.url === "string" && productAt(sender.url) !== null;
}

export function allowedPopupSender(sender: chrome.runtime.MessageSender): boolean {
  return sender.id === chrome.runtime.id && !sender.tab && sender.url === chrome.runtime.getURL("popup.html");
}

async function nativeRequest(request: NativeRequest): Promise<HostResponse> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const result: HostResponse = await Promise.race([
      chrome.runtime.sendNativeMessage(HOST, request),
      new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error("Local lookup timed out")), 10000); })
    ]);
    if (!result || result.schema_version !== 1 || (result.result !== "error" && result.request_id !== request.request_id)) throw new Error("Invalid host response");
    return result;
  } finally {
    clearTimeout(timer);
  }
}

async function nativeCheck(candidate: unknown, requestId: string): Promise<HostResponse> {
  if (!candidate || typeof candidate !== "object" || JSON.stringify(candidate).length > 32 * 1024) throw new Error("Invalid candidate");
  return nativeRequest({ schema_version: 1, request_id: requestId, operation: "check", candidate: candidate as Candidate });
}

export async function handleMessage(message: unknown, sender: chrome.runtime.MessageSender): Promise<unknown> {
  if (!message || typeof message !== "object") throw new Error("Invalid message");
  const data = message as Record<string, unknown>;
  if (data.type === "check") {
    if (!allowedContentSender(sender, chrome.runtime.id)) throw new Error("Sender not allowed");
    if (typeof data.requestId !== "string" || data.requestId.length > 100) throw new Error("Invalid request ID");
    const result = await nativeCheck(data.candidate, data.requestId);
    // Only this summary crosses into the page's content script.
    return { requestId: data.requestId, result: result.result,
      label: result.result === "error" ? "確認できません" : result.label };
  }
  if (data.type === "status" || data.type === "details") {
    if (!allowedPopupSender(sender)) throw new Error("Sender not allowed");
    if (data.type === "status") return nativeRequest({ schema_version: 1, request_id: crypto.randomUUID(), operation: "status" });
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.id === undefined || !tab.url || !productAt(tab.url)) return {
      schema_version: 1, result: "unsupported_page", label: "対応サイトの商品ページを開いてください。"
    };
    let candidate: unknown;
    try {
      candidate = await chrome.tabs.sendMessage(tab.id, { type: "get-candidate" });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      return { schema_version: 1, result: "error", error: { code: "page_unavailable", message: `商品ページと通信できません。拡張機能を再読み込みした後、商品ページも再読み込みしてください。\n詳細：${detail}` } };
    }
    if (!candidate) return { schema_version: 1, result: "unidentified", label: "確認できません",
      error: { code: "product_unidentified", message: "商品情報を読み取れません。商品詳細ページを再読み込みしてください。" } };
    return nativeCheck(candidate, crypto.randomUUID());
  }
  throw new Error("Unsupported operation");
}
