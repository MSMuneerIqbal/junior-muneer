"use client";

import { useSyncExternalStore } from "react";

/** Whether the sidebars are hidden on big screens. Remembered in this browser. */

type Side = "left" | "right";
const KEY = { left: "hideLeftSidebar", right: "hideRightPanel" } as const;
const EVENT = "layoutprefs";

function read(side: Side): boolean {
  try {
    return localStorage.getItem(KEY[side]) === "1";
  } catch {
    return false;
  }
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

export function setHidden(side: Side, hidden: boolean) {
  try {
    if (hidden) localStorage.setItem(KEY[side], "1");
    else localStorage.removeItem(KEY[side]);
  } catch {}
  window.dispatchEvent(new Event(EVENT));
}

export function useHidden(side: Side): boolean {
  return useSyncExternalStore(subscribe, () => read(side), () => false);
}
