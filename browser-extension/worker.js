// Only fixed commands are accepted. Page text is never interpreted as a command.
let socket = null;
let ownedTab = null;
let ownedVideoId = null;
let mediaEpoch = 0;
let heartbeat = null;
let connected = false;
let connectionState = "disconnected";
let connectionEpoch = 0;
const validId = (value) => typeof value === "string" && /^[A-Za-z0-9_-]{11}$/.test(value);
function isVideo(tab, videoId) {
  try {
    const value = (!tab.url || tab.url === "about:blank" || tab.url.startsWith("chrome://newtab")) ? tab.pendingUrl : tab.url;
    const url = new URL(value || "");
    return url.origin === "https://www.youtube.com" && url.pathname === "/watch" && url.searchParams.get("v") === videoId;
  } catch { return false; }
}
const isOwnedVideo = (tab) => isVideo(tab, ownedVideoId);

function disconnect() {
  connectionEpoch++;
  mediaEpoch++;
  connected = false;
  connectionState = "disconnected";
  if (heartbeat) clearInterval(heartbeat);
  heartbeat = null;
  const old = socket;
  socket = null;
  if (old) old.close();
}

async function connect() {
  disconnect();
  const epoch = connectionEpoch;
  const { pairing } = await chrome.storage.local.get("pairing");
  if (epoch !== connectionEpoch) return;
  if (typeof pairing !== "string") return;
  connectionState = "connecting";
  const current = new WebSocket("ws://127.0.0.1:8000/api/computer/signed-browser/ws");
  socket = current;
  current.onopen = () => {
    current.send(JSON.stringify({ token: pairing }));
    heartbeat = setInterval(() => {
      if (socket === current && current.readyState === WebSocket.OPEN) current.send('{"ping":true}');
    }, 20000);
  };
  current.onclose = () => { if (socket === current) { disconnect(); connectionState = "failed"; } };
  current.onerror = () => { if (socket === current) { disconnect(); connectionState = "failed"; } };
  current.onmessage = async (event) => {
    if (socket !== current) return;
    let message;
    try { message = JSON.parse(event.data); } catch { current.close(); return; }
    if (message.connected === true) { connected = true; connectionState = "connected"; return; }
    if (message.pong === true) return;
    if (!connected || !/^[a-f0-9]{32}$/.test(message.id || "")) { current.close(); return; }
    let result;
    try { result = await run(message.command, message.payload, () => socket === current && connected); }
    catch { result = { outcome: "unclear", detail: "The browser could not confirm the action. Check the tab before retrying." }; }
    if (socket === current && current.readyState === WebSocket.OPEN) current.send(JSON.stringify({ id: message.id, result }));
  };
}

async function waitForPlayback(tabId, videoId, epoch, alive) {
  const started = Date.now();
  let previous = 0;
  while (Date.now() - started < 55000) {
    if (!alive() || epoch !== mediaEpoch) return { outcome: "failed", detail: "The player action was stopped." };
    const tab = await chrome.tabs.get(tabId);
    let current;
    try { current = new URL(tab.url || ""); } catch { await new Promise((r) => setTimeout(r, 500)); continue; }
    if (tab.status === "loading" && current.origin !== "https://www.youtube.com") { await new Promise((r) => setTimeout(r, 500)); continue; }
    if (current.origin !== "https://www.youtube.com" || current.pathname !== "/watch" || current.searchParams.get("v") !== videoId)
      return { outcome: "unclear", detail: "The YouTube tab changed; playback was not confirmed." };
    if (tab.status === "complete") {
      let result;
      try { [result] = await chrome.scripting.executeScript({ target: { tabId }, func: () => {
        const video = document.querySelector("video");
        if (document.querySelector(".html5-video-player.ad-showing")) return 0;
        if (video && video.paused) void video.play().catch(() => {});
        return video && !video.paused && !video.muted && video.volume > 0 ? video.currentTime : 0;
      }}); } catch { await new Promise((r) => setTimeout(r, 500)); continue; }
      const now = typeof result.result === "number" ? result.result : 0;
      if (previous > 0 && now > previous + 0.2) return { outcome: "sent", detail: "YouTube playback is running in your Chrome tab." };
      previous = now;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return { outcome: "unclear", detail: "YouTube opened, but playback was not confirmed. Check the Chrome tab." };
}

async function run(command, payload, alive) {
  if (!alive()) throw Error("Disconnected");
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw Error("Invalid command");
  if (command === "media_play") {
    if (Object.keys(payload).length !== 1 || !validId(payload.video_id)) throw Error("Invalid video");
    const epoch = ++mediaEpoch;
    // A new owned tab avoids navigating or closing any existing personal tab.
    if (ownedTab !== null) {
      try { const previous = await chrome.tabs.get(ownedTab); if (alive() && epoch === mediaEpoch && isOwnedVideo(previous)) await chrome.tabs.remove(ownedTab); } catch {}
      ownedTab = null; ownedVideoId = null;
    }
    if (!alive() || epoch !== mediaEpoch) return { outcome: "failed", detail: "The player action was stopped." };
    const tab = await chrome.tabs.create({ url: "https://www.youtube.com/watch?v=" + payload.video_id, active: true });
    if (!alive() || epoch !== mediaEpoch) {
      try { if (isVideo(await chrome.tabs.get(tab.id), payload.video_id)) await chrome.tabs.remove(tab.id); } catch {}
      return { outcome: "failed", detail: "The player action was stopped." };
    }
    ownedTab = tab.id;
    ownedVideoId = payload.video_id;
    return await waitForPlayback(ownedTab, payload.video_id, epoch, alive);
  }
  if (command === "media_stop") {
    mediaEpoch++;
    if (Object.keys(payload).length || ownedTab === null) return { outcome: "failed", detail: "Junior has no owned YouTube tab." };
    const tab = ownedTab;
    if (!isOwnedVideo(await chrome.tabs.get(tab))) {
      ownedTab = null; ownedVideoId = null;
      return { outcome: "failed", detail: "The tab changed, so Junior left it open." };
    }
    if (!alive()) return { outcome: "failed", detail: "The browser disconnected." };
    ownedTab = null; ownedVideoId = null;
    await chrome.tabs.remove(tab);
    return { outcome: "sent", detail: "Closed Junior's YouTube tab." };
  }
  if (command === "media_status") {
    if (Object.keys(payload).length || ownedTab === null) return { outcome: "failed", state: "missing" };
    const tab = await chrome.tabs.get(ownedTab);
    if (!isOwnedVideo(tab)) return { outcome: "failed", state: "changed" };
    const [result] = await chrome.scripting.executeScript({ target: { tabId: ownedTab }, func: () => {
      const video = document.querySelector("video"), error = document.querySelector(".ytp-error-content-wrap");
      if (video?.error || (error && error.offsetParent !== null)) return "error";
      return video && !video.paused && video.currentTime > 1 ? "playing" : "paused";
    }});
    return { outcome: "sent", state: result.result };
  }
  if (command === "media_next") {
    if (Object.keys(payload).length || ownedTab === null) return { outcome: "failed", detail: "Junior has no owned YouTube tab." };
    const tab = await chrome.tabs.get(ownedTab);
    const current = new URL(tab.url || "");
    if (!isOwnedVideo(tab) || !validId(current.searchParams.get("v")))
      return { outcome: "failed", detail: "Junior's YouTube tab changed." };
    const [result] = await chrome.scripting.executeScript({ target: { tabId: ownedTab }, func: () => document.querySelector("a.ytp-next-button")?.href || "" });
    const next = new URL(result.result || "", "https://www.youtube.com");
    const id = next.searchParams.get("v");
    if (next.origin !== "https://www.youtube.com" || next.pathname !== "/watch" || !validId(id) || id === current.searchParams.get("v"))
      return { outcome: "failed", detail: "YouTube did not provide a usable next video." };
    const checked = await chrome.tabs.get(ownedTab);
    if (!alive() || !isOwnedVideo(checked)) return { outcome: "failed", detail: "The YouTube tab changed or disconnected." };
    const epoch = ++mediaEpoch;
    await chrome.tabs.update(ownedTab, { url: "https://www.youtube.com/watch?v=" + id, active: true });
    ownedVideoId = id;
    return await waitForPlayback(ownedTab, id, epoch, alive);
  }
  return { outcome: "failed", detail: "This operation is not available in the signed-in browser yet." };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "status") { sendResponse({ state: connectionState }); return; }
  if (message?.type === "connect") void connect();
  if (message?.type === "disconnect") {
    if (connected && socket?.readyState === WebSocket.OPEN) socket.send('{"unpair":true}');
    disconnect();
  }
});
chrome.alarms.create("reconnect", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => { if (alarm.name === "reconnect" && !socket) void connect(); });
void connect();
