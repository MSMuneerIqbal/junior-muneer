const code = document.getElementById("code");
const status = document.getElementById("status");
async function refreshStatus() {
  try {
    const { state } = await chrome.runtime.sendMessage({ type: "status" });
    status.textContent = {
      connected: "Connected to Junior on this computer.",
      connecting: "Connecting to Junior on this computer…",
      failed: "Could not connect. Check Junior is running, then generate a new pairing code and try again.",
      disconnected: "Not connected. Paste a pairing code to connect.",
    }[state] || "Not connected.";
  } catch { status.textContent = "Could not reach the extension. Reload it in chrome://extensions."; }
}
document.getElementById("pair").addEventListener("click", async () => {
  const value = code.value.trim();
  code.value = "";
  if (!/^[A-Za-z0-9_-]{40,100}$/.test(value)) { status.textContent = "Check the pairing code."; return; }
  await chrome.storage.local.set({ pairing: value });
  await chrome.runtime.sendMessage({ type: "connect" });
  status.textContent = "Connecting to Junior on this computer…";
  setTimeout(refreshStatus, 500);
});
document.getElementById("disconnect").addEventListener("click", async () => {
  await chrome.storage.local.remove("pairing");
  await chrome.runtime.sendMessage({ type: "disconnect" });
  status.textContent = "Disconnected here. To revoke access when Junior is offline, also choose Disconnect Chrome in Junior settings.";
});
void refreshStatus();
setInterval(refreshStatus, 1000);
