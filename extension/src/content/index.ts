import { extractCandidate } from "../adapters";
import { PageController } from "./controller";
import { watchPage } from "./watch";

const controller = new PageController(document, () => location.href, message => chrome.runtime.sendMessage(message));
void controller.refresh();
watchPage(document, force => { void controller.refresh(force); }, () => location.href);
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id === chrome.runtime.id && message?.type === "get-candidate") respond(extractCandidate(document, location.href));
});
