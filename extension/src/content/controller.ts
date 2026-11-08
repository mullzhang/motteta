import { extractCandidate, insertionAnchor, productAt } from "../adapters";
import type { Candidate } from "../generated/native-request";

export class PageController {
  private serial = 0;
  private signature: string | null = null;
  private identity: string | null = null;
  private format: Candidate["format"] | null = null;
  private pending = false;
  private badge: HTMLElement | null = null;
  constructor(private doc: Document, private href: () => string,
    private send: (message: unknown) => Promise<{ result: string; label?: string }>) {}

  async refresh(force = false): Promise<void> {
    const href = this.href();
    const product = productAt(href);
    const candidate = extractCandidate(this.doc, href);
    const signature = JSON.stringify({ product, candidate });
    const identity = JSON.stringify(candidate
      ? { source: product?.source, identifiers: candidate.identifiers }
      : product);
    const format = candidate && candidate.format !== "unknown" ? candidate.format : null;
    const changedProduct = identity !== this.identity;
    const changedFormat = format !== null && this.format !== null && format !== this.format;
    const title = product ? insertionAnchor(this.doc, href) : null;
    if (changedProduct || changedFormat || !title) {
      this.badge?.remove();
      this.badge = null;
    } else if (this.badge && this.badge.previousElementSibling !== title) {
      title.insertAdjacentElement("afterend", this.badge);
    }
    this.identity = identity;
    if (changedProduct) this.format = null;
    if (format) this.format = format;
    if (signature === this.signature && (this.pending || (!force && (!product || this.badge?.isConnected)))) return;
    this.signature = signature;
    const serial = ++this.serial;
    this.pending = false;
    if (!product || !title) return;
    if (!candidate) { this.show(href, "確認できません"); return; }
    this.pending = true;
    let label: string;
    try {
      const result = await this.send({ type: "check", requestId: crypto.randomUUID(), candidate });
      label = result.result === "error" ? "確認できません" : result.label ?? "確認できません";
    } catch {
      label = "確認できません";
    }
    if (serial !== this.serial) return;
    this.pending = false;
    const currentHref = this.href();
    if (signature !== JSON.stringify({ product: productAt(currentHref), candidate: extractCandidate(this.doc, currentHref) })) {
      await this.refresh();
      return;
    }
    this.show(currentHref, label);
  }

  private show(href: string, label: string): void {
    const title = insertionAnchor(this.doc, href);
    if (!title) return;
    if (!this.badge) {
      this.badge = this.doc.createElement("aside");
      this.badge.dataset.motteta = "badge";
      this.badge.setAttribute("role", "status");
      this.badge.style.cssText = "padding:10px 14px;margin:10px 0;border:1px solid #347059;border-radius:6px;background:#f2faf5;color:#174633;font:14px/1.5 sans-serif;";
    }
    const value = "Motteta：" + label;
    if (this.badge.textContent !== value) this.badge.textContent = value;
    if (this.badge.previousElementSibling !== title) title.insertAdjacentElement("afterend", this.badge);
  }
}
