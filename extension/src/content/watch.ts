/** Observe product mutations, visibility, and history changes without page-world code. */
export function watchPage(doc: Document, refresh: (force: boolean) => void, href: () => string): () => void {
  const view = doc.defaultView!;
  let timer: ReturnType<typeof setTimeout>;
  const observer = new MutationObserver(changes => {
    const onlyBadges = changes.every(change => {
      const element = change.target instanceof Element ? change.target : change.target.parentElement;
      if (element?.closest("[data-motteta]")) return true;
      if (change.type !== "childList") return false;
      const nodes = [...change.addedNodes, ...change.removedNodes];
      return nodes.length > 0 && nodes.every(n => n instanceof Element && n.matches("[data-motteta]"));
    });
    if (onlyBadges) return;
    clearTimeout(timer);
    timer = setTimeout(() => refresh(false), 150);
  });
  observer.observe(doc.body, { subtree: true, childList: true, attributes: true, characterData: true });
  const visible = () => { if (!doc.hidden) refresh(true); };
  const popstate = () => refresh(false);
  doc.addEventListener("visibilitychange", visible);
  view.addEventListener("popstate", popstate);
  let previousUrl = href();
  const interval = setInterval(() => {
    const current = href();
    if (current !== previousUrl) { previousUrl = current; refresh(false); }
  }, 1000);
  return () => {
    observer.disconnect(); clearTimeout(timer); clearInterval(interval);
    doc.removeEventListener("visibilitychange", visible);
    view.removeEventListener("popstate", popstate);
  };
}
