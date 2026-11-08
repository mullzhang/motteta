import type { HostResponse } from "../background/handler";

const stateLabels: Record<string, string> = { print: "紙", digital: "電子", unknown: "不明", completed: "購入完了", ordered: "注文中", preordered: "予約中", cancelled: "キャンセル済み", returned: "返品済み", owned: "所持", disposed: "手放した", gift: "贈答用" };
function label(value: string | null): string { return value === null ? "該当なし" : stateLabels[value] ?? value; }
function paragraph(parent: Element, text: string): void {
  const p = document.createElement("p"); p.textContent = text; parent.append(p);
}
async function showConnection(): Promise<void> {
  const connection = document.querySelector("#connection")!;
  try {
    const result: HostResponse = await chrome.runtime.sendMessage({ type: "status" });
    if (result.result !== "ok") throw new Error(result.error?.message ?? "台帳の応答を確認してください");
    connection.textContent = "ローカル台帳：接続済み";
  } catch (error) {
    connection.textContent = "ローカル台帳：接続できません";
    document.querySelector("#connection-error")!.textContent = error instanceof Error ? error.message : "接続設定を確認してください";
  }
}
async function show(): Promise<void> {
  try {
    const result: HostResponse = await chrome.runtime.sendMessage({ type: "details" });
    if (result.result === "error") throw new Error(result.error?.message ?? result.label ?? "接続を確認してください");
    document.querySelector("#status")!.textContent = result.label ?? "確認できません";
    if (result.result === "unsupported_page") return;
    if (result.result === "unidentified") {
      document.querySelector("#error")!.textContent = result.error?.message ?? "";
      return;
    }
    for (const match of result.matches ?? []) {
      const record = match.record;
      const card = document.createElement("article");
      paragraph(card, record.book.title);
      paragraph(card, `${label(record.book.format)} / ${record.source?.name ?? "購入先不明"} / ${record.acquired_on ?? "購入日不明"} / ${record.quantity}冊`);
      paragraph(card, `注文：${label(record.order_state)}　所持：${label(record.possession_state)}`);
      paragraph(card, `照合：${{exact:"識別子と形態が一致",related:"同じ作品として確認済み",possible:"同じ本の可能性"}[match.kind] ?? match.kind}`);
      document.querySelector("#records")!.append(card);
    }
    const freshness = document.querySelector("#freshness")!;
    for (const source of result.freshness?.sources ?? []) {
      paragraph(freshness, `${source.source.name} (${source.account})：直近の取得完了 ${source.last_complete ?? "未確認"}`);
      for (const range of source.confirmed_ranges) paragraph(freshness, `確認済み期間：${range.requested_start} 〜 ${range.requested_end}`);
      if (source.last_attempt) {
        const coverage = source.last_attempt.coverage;
        paragraph(freshness, `直近の取得：${source.last_attempt.observed_at} (${coverage.status})／未確認 ${coverage.unverified.length}件`);
        if (coverage.checked_start) paragraph(freshness, `直近の確認範囲：${coverage.checked_start} 〜 ${coverage.checked_end}`);
      }
    }
    if (!result.freshness?.sources.length) paragraph(freshness, "取得範囲は未登録です。");
  } catch (error) {
    document.querySelector("#status")!.textContent = "確認できません";
    document.querySelector("#error")!.textContent = error instanceof Error ? error.message : "ローカル接続を確認してください";
  }
}
void showConnection();
void show();
