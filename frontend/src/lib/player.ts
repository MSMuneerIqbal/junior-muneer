"use client";

import { useSyncExternalStore } from "react";
import { BACKEND_URL } from "@/lib/api";

/** One audio player for the whole app, so only one answer plays at a time. */

type State = { messageId: number | null; status: "idle" | "loading" | "playing"; error?: string };

let state: State = { messageId: null, status: "idle" };
let audio: HTMLAudioElement | null = null;
const listeners = new Set<() => void>();

function set(next: State) {
  state = next;
  listeners.forEach((l) => l());
}

export function stopSpeaking() {
  if (audio) {
    audio.onerror = null;
    audio.pause();
    audio.removeAttribute("src");
  }
  audio = null;
  set({ messageId: null, status: "idle" });
}

/** Why the speech didn't play (the backend explains, e.g. the daily cap). */
async function reason(url: string): Promise<string> {
  try {
    const res = await fetch(url);
    if (!res.ok) return (await res.json()).detail ?? `Couldn't read aloud (${res.status})`;
  } catch {}
  return "Couldn't read aloud. See the Activity page.";
}

/**
 * Read one of his answers aloud. The backend streams the speech while it's made
 * (it starts in ~2 seconds) and keeps it, so the next time is instant and free.
 */
export async function speakMessage(messageId: number) {
  stopSpeaking();
  const url = `${BACKEND_URL}/api/voice/speak/${messageId}.mp3`;
  const el = new Audio(url);
  audio = el;
  set({ messageId, status: "loading" });
  el.onplaying = () => audio === el && set({ messageId, status: "playing" });
  el.onended = () => audio === el && set({ messageId: null, status: "idle" });
  el.onerror = async () => {
    if (audio !== el) return;
    audio = null;
    set({ messageId, status: "idle", error: await reason(url) });
  };
  try {
    await el.play();
  } catch (e) {
    // Browsers may block sound until you've clicked on the page once.
    if (audio === el && e instanceof DOMException && e.name === "NotAllowedError") {
      audio = null;
      set({ messageId, status: "idle", error: "Tap 🔊 Listen to hear it" });
    }
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const idle: State = { messageId: null, status: "idle" };

export function usePlayer(): State {
  return useSyncExternalStore(subscribe, () => state, () => idle);
}
