const APP_BASE = "http://localhost:54321";

// Injected into the claude.ai tab's main world — same-origin fetch works here
async function fetchUsageInPage() {
  const ENDPOINTS = [
    "/api/usage_limits",
    "/api/account/usage",
    "/api/billing/usage_limits",
  ];
  for (const path of ENDPOINTS) {
    try {
      const r = await fetch(path, { credentials: "include", headers: { Accept: "application/json" } });
      if (r.ok) return { data: await r.json(), endpoint: path };
    } catch (_) {}
  }
  return null;
}

async function pushKey() {
  try {
    const cookie = await chrome.cookies.get({ url: "https://claude.ai", name: "sessionKey" });
    if (!cookie?.value) return;
    await fetch(`${APP_BASE}/session-key`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: cookie.value }),
    });
  } catch (_) {}
}

async function pushUsageFromTab(tabId) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      world: "MAIN",
      func: fetchUsageInPage,
    });
    const result = results?.[0]?.result;
    if (!result?.data) return;

    await fetch(`${APP_BASE}/data`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ usage: result.data, endpoint: result.endpoint }),
    });
  } catch (_) {}
}

// When user navigates to claude.ai — inject and fetch
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.url?.includes("claude.ai")) {
    pushUsageFromTab(tabId);
    pushKey();
  }
});

// On startup: push key and fetch from any open claude.ai tab
(async () => {
  pushKey();
  const tabs = await chrome.tabs.query({ url: "https://claude.ai/*" });
  for (const tab of tabs) pushUsageFromTab(tab.id);
})();

// Every 5 min: push key + fetch from open claude.ai tab
chrome.alarms.create("refresh", { periodInMinutes: 5 });
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== "refresh") return;
  pushKey();
  const tabs = await chrome.tabs.query({ url: "https://claude.ai/*" });
  for (const tab of tabs) pushUsageFromTab(tab.id);
});

// On sessionKey cookie change
chrome.cookies.onChanged.addListener(({ cookie, removed }) => {
  if (cookie.name === "sessionKey" && cookie.domain.includes("claude.ai") && !removed) {
    pushKey();
  }
});
