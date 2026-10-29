const code = document.getElementById("code");
const status = document.getElementById("status");
document.getElementById("pair").addEventListener("click", async () => {
  const value = code.value.trim();
  code.value = "";
  if (!/^[A-Za-z0-9_-]{40,100}$/.test(value)) { status.textContent = "Check the pairing code."; return; }
  await chrome.storage.local.set({ pairing: value });
  await chrome.runtime.sendMessage({ type: "connect" });
  status.textContent = "Connecting to Junior on this computer…";
});
document.getElementById("disconnect").addEventListener("click", async () => {
  await chrome.storage.local.remove("pairing");
  await chrome.runtime.sendMessage({ type: "disconnect" });
  status.textContent = "Disconnected here. To revoke access when Junior is offline, also choose Disconnect Chrome in Junior settings.";
});
