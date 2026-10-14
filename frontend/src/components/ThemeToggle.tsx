"use client";

import { useSyncExternalStore } from "react";

type Theme = "system" | "light" | "dark";
const ORDER: Theme[] = ["system", "light", "dark"];
const LABEL: Record<Theme, string> = { system: "◐", light: "☀", dark: "☾" };
const EVENT = "themechange";

function readTheme(): Theme {
  try {
    const saved = localStorage.getItem("theme");
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch {
    return "system";
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

/** Cycles System → Light → Dark. The choice is saved in this browser. */
export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, readTheme, () => "system" as Theme);

  function next() {
    const t = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length];
    const root = document.documentElement;
    try {
      if (t === "system") {
        root.removeAttribute("data-theme");
        localStorage.removeItem("theme");
      } else {
        root.setAttribute("data-theme", t);
        localStorage.setItem("theme", t);
      }
    } catch {}
    window.dispatchEvent(new Event(EVENT));
  }

  return (
    <button
      onClick={next}
      className="rounded-md px-2 py-1 text-muted hover:bg-panel-2"
      title={`Theme: ${theme} (click to change)`}
      aria-label={`Theme: ${theme}`}
    >
      {LABEL[theme]}
    </button>
  );
}
