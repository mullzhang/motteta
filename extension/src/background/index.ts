import { allowedPopupSender, handleMessage, type HostResponse } from "./handler";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender).then(sendResponse).catch(error => {
    const response: HostResponse = { schema_version: 1, result: "error", label: "確認できません" };
    if (allowedPopupSender(sender)) response.error = {
      code: "extension_error", message: error instanceof Error ? error.message : "ローカル接続を確認してください"
    };
    sendResponse(response);
  });
  return true;
});
