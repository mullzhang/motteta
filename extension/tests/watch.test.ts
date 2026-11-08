// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { watchPage } from "../src/content/watch";

afterEach(() => vi.useRealTimers());

it("refreshes after an attribute-only product change and ignores badge mutations", async () => {
  vi.useFakeTimers();
  document.body.innerHTML = '<main><input id="ASIN" value="B0TEST0001"><aside data-motteta="badge">Motteta</aside></main>';
  const refresh = vi.fn();
  const stop = watchPage(document, refresh, () => "https://www.amazon.co.jp/dp/B0TEST0001");
  document.querySelector("#ASIN")!.setAttribute("value", "B0TEST0002");
  await vi.advanceTimersByTimeAsync(200);
  expect(refresh).toHaveBeenCalledExactlyOnceWith(false);
  document.querySelector("aside")!.textContent = "Updated badge";
  await vi.advanceTimersByTimeAsync(200);
  expect(refresh).toHaveBeenCalledTimes(1);
  stop();
});

it("notices a history URL change even without a DOM mutation", async () => {
  vi.useFakeTimers();
  let url = "https://www.amazon.co.jp/dp/B0TEST0001";
  const refresh = vi.fn();
  const stop = watchPage(document, refresh, () => url);
  url = "https://www.amazon.co.jp/dp/B0TEST0002";
  await vi.advanceTimersByTimeAsync(1100);
  expect(refresh).toHaveBeenCalledExactlyOnceWith(false);
  stop();
});
