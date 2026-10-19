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

/** The theme and a function that moves to the next one (System → Light → Dark), saved in this browser. */
export function useTheme(): [Theme, () => void] {
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

  return [theme, next];
}

export const THEME_NAMES: Record<Theme, string> = { system: "System", light: "Light", dark: "Dark" };

/** A small button that cycles the theme. */
export function ThemeToggle() {
  const [theme, next] = useTheme();
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
