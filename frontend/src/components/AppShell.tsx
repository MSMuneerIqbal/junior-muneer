"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import useSWR from "swr";
import { ChatHistory } from "@/components/ChatHistory";
import { NavIcon, SidebarLeftIcon, SidebarRightIcon } from "@/components/icons";
import { THEME_NAMES, useTheme } from "@/components/ThemeToggle";
import { fetcher } from "@/lib/api";
import { SETTINGS_KEY } from "@/lib/keys";
import type { Settings } from "@/lib/types";
import { TodayPanel } from "@/components/TodayPanel";
import { WaitingBadge } from "@/components/approvals/WaitingBadge";
import { setHidden, useHidden } from "@/lib/layoutPrefs";

// The features, at the top of the sidebar. Profile and Settings are in your menu at the bottom.
const NAV = [
  { href: "/", label: "New chat", icon: "newchat" },
  { href: "/approvals", label: "Approvals", icon: "approvals" },
  { href: "/inbox", label: "Inbox", icon: "inbox" },
  { href: "/social", label: "Social", icon: "social" },
  { href: "/freelance", label: "Freelance", icon: "freelance" },
  { href: "/news", label: "News", icon: "news" },
  { href: "/notes", label: "Notes", icon: "notes" },
  { href: "/memory", label: "Memory", icon: "memory" },
  { href: "/activity", label: "Activity", icon: "activity" },
];

/** You, at the bottom of the sidebar: a menu with Profile, Settings and the theme (like ChatGPT's). */
function YouMenu() {
  const { data } = useSWR<Settings>(SETTINGS_KEY, fetcher);
  const [open, setOpen] = useState(false);
  const [theme, nextTheme] = useTheme();
  const box = useRef<HTMLDivElement>(null);
  const name = data?.user_name || "You";
  const initials = name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const item = "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-[14px] hover:bg-panel-2";
  return (
    <div ref={box} className="relative border-t border-line p-2">
      {open && (
        <div role="menu" aria-label="Your menu" className="absolute inset-x-2 bottom-full mb-2 rounded-2xl border border-line bg-panel p-1.5 shadow-xl">
          <Link role="menuitem" href="/profile" onClick={() => setOpen(false)} className={item}>
            <NavIcon name="profile" className="h-[18px] w-[18px]" />
            Profile
          </Link>
          <Link role="menuitem" href="/settings" onClick={() => setOpen(false)} className={item}>
            <NavIcon name="settings" className="h-[18px] w-[18px]" />
            Settings
          </Link>
          <button role="menuitem" type="button" onClick={nextTheme} className={item}>
            <NavIcon name="theme" className="h-[18px] w-[18px]" />
            Theme
            <span className="ml-auto text-xs text-muted">{THEME_NAMES[theme]}</span>
          </button>
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label="Open your menu"
        className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-panel-2"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-fg">
          {initials}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14px] font-medium">{name}</span>
          <span className="block text-xs text-muted">Profile, settings, theme</span>
        </span>
      </button>
    </div>
  );
}

// Where each side panel stops being a drawer and sits beside the chat (Tailwind lg / xl).
const LEFT_DOCKED = "(min-width: 1024px)";
const RIGHT_DOCKED = "(min-width: 1280px)";

const iconButton =
  "flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-panel-2 hover:text-ink";

/**
 * Three columns: sidebar · main · Today panel. On big screens either side can be
 * hidden (remembered); on a phone the side panels are drawers.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const leftHidden = useHidden("left");
  const rightHidden = useHidden("right");
  // A drawer stays open only on the page where it was opened, so navigating closes it.
  const [openDrawer, setOpenDrawer] = useState<{ side: "left" | "right"; path: string } | null>(
    null,
  );
  const [searching, setSearching] = useState(false);
  const [query, setQuery] = useState("");
  const leftOpen = openDrawer?.side === "left" && openDrawer.path === pathname;
  const rightOpen = openDrawer?.side === "right" && openDrawer.path === pathname;
  const setLeftOpen = (open: boolean) => setOpenDrawer(open ? { side: "left", path: pathname } : null);
  const setRightOpen = (open: boolean) =>
    setOpenDrawer(open ? { side: "right", path: pathname } : null);

  const docked = (query: string) => window.matchMedia(query).matches;

  // Settings is its own full page (its own left menu, and a link back to the chat).
  if (pathname.startsWith("/settings")) return <div className="h-dvh overflow-hidden">{children}</div>;
  const hideLeft = () => (docked(LEFT_DOCKED) ? setHidden("left", true) : setLeftOpen(false));
  const hideRight = () => (docked(RIGHT_DOCKED) ? setHidden("right", true) : setRightOpen(false));
  const showRight = () => {
    if (docked(RIGHT_DOCKED)) setHidden("right", false);
    else setRightOpen(true);
  };

  return (
    <div className="flex h-dvh overflow-hidden">
      {(leftOpen || rightOpen) && (
        <button
          aria-label="Close panel"
          className={`fixed inset-0 z-30 bg-black/30 ${rightOpen ? "xl:hidden" : "lg:hidden"}`}
          onClick={() => setOpenDrawer(null)}
        />
      )}

      <aside
        onClick={(e) => {
          // Picking a chat or page closes the drawer on phones.
          if ((e.target as HTMLElement).closest("a")) setLeftOpen(false);
        }}
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-line bg-panel transition-transform lg:static lg:translate-x-0 ${
          leftOpen ? "translate-x-0" : "-translate-x-full"
        } ${leftHidden ? "lg:hidden" : ""}`}
      >
        {/* Like ChatGPT's sidebar: name and buttons, New chat, the features, then your chats; you at the bottom. */}
        <div className="flex items-center gap-1 px-4 pt-4 pb-2">
          <Link href="/" className="mr-auto text-[17px] font-semibold tracking-tight">
            Junior Muneer
          </Link>
          <button
            onClick={() => setSearching((s) => !s)}
            className={iconButton}
            aria-label="Search chats"
            aria-pressed={searching}
            title="Search chats"
          >
            <NavIcon name="search" className="h-[18px] w-[18px]" />
          </button>
          <button onClick={hideLeft} className={iconButton} aria-label="Hide sidebar" title="Hide sidebar">
            <SidebarLeftIcon className="h-[18px] w-[18px]" />
          </button>
        </div>
        {searching && (
          <div className="px-3 pb-2">
            <input
              autoFocus
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setQuery("");
                  setSearching(false);
                }
              }}
              placeholder="Search chats"
              aria-label="Search text"
              dir="auto"
              className="w-full rounded-lg border border-line bg-bg px-3 py-1.5 text-sm outline-none focus:border-accent"
            />
          </div>
        )}

        {/* One scroll for the features and your chats, like ChatGPT. */}
        <div className="min-h-0 flex-1 overflow-y-auto px-2">
          <nav aria-label="Main" className="flex shrink-0 flex-col gap-0.5 pb-3">
            {NAV.map((item) => {
              const active = item.href !== "/" && pathname.startsWith(item.href); // the open chat is marked in Recents
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 rounded-lg px-3 py-[7px] text-[15px] ${
                    active ? "bg-panel-2 text-ink" : "text-ink/85 hover:bg-panel-2/70 hover:text-ink"
                  }`}
                >
                  <NavIcon name={item.icon} className="h-[18px] w-[18px] shrink-0" />
                  {item.label}
                  {item.href === "/approvals" && <WaitingBadge />}
                </Link>
              );
            })}
          </nav>
          <Suspense>
            <ChatHistory query={searching ? query : ""} />
          </Suspense>
        </div>

        <YouMenu />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Phone: menu and Today buttons. */}
        <header className="flex items-center justify-between border-b border-line bg-panel px-3 py-2 lg:hidden">
          <button className={iconButton} aria-label="Open chats and menu" onClick={() => setLeftOpen(true)}>
            <SidebarLeftIcon />
          </button>
          <span className="font-semibold">Junior Muneer</span>
          <button className={iconButton} aria-label="Open today panel" onClick={() => setRightOpen(true)}>
            <SidebarRightIcon />
          </button>
        </header>
        {/* Big screens: buttons to bring back a hidden side panel. */}
        <div
          className={`hidden items-center justify-between border-b border-line px-2 py-1 lg:flex ${
            !leftHidden && !rightHidden ? "xl:hidden" : ""
          }`}
        >
          {leftHidden ? (
            <button
              onClick={() => setHidden("left", false)}
              className={iconButton}
              aria-label="Show sidebar"
              title="Show sidebar"
            >
              <SidebarLeftIcon className="h-[18px] w-[18px]" />
            </button>
          ) : (
            <span />
          )}
          <button
            onClick={showRight}
            className={`${iconButton} ${rightHidden ? "" : "xl:hidden"}`}
            aria-label="Show today panel"
            title="Show today panel"
          >
            <SidebarRightIcon className="h-[18px] w-[18px]" />
          </button>
        </div>
        <main className="min-h-0 flex-1">{children}</main>
      </div>

      <aside
        className={`fixed inset-y-0 right-0 z-40 w-72 border-l border-line bg-panel transition-transform xl:static xl:translate-x-0 ${
          rightOpen ? "translate-x-0" : "translate-x-full"
        } ${rightHidden ? "xl:hidden" : ""}`}
      >
        <button
          onClick={hideRight}
          className={`${iconButton} absolute top-3 right-3`}
          aria-label="Hide today panel"
          title="Hide today panel"
        >
          <SidebarRightIcon className="h-[18px] w-[18px]" />
        </button>
        <TodayPanel />
      </aside>
    </div>
  );
}
