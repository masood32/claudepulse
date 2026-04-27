// Content script — runs on claude.ai pages in isolated world
// Fetches usage data from the page's own API and sends to local tracker app

(async function () {
  const ENDPOINTS = [
    "/api/usage_limits",
    "/api/account/usage",
    "/api/billing/usage_limits",
  ];

  for (const path of ENDPOINTS) {
    try {
      const r = await fetch(`https://claude.ai${path}`, {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (r.ok) {
        const data = await r.json();
        // Send to background script which forwards to local app
        chrome.runtime.sendMessage({ type: "usage_data", data, endpoint: path });
        return;
      }
    } catch (_) {}
  }
})();
