"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useState, type ReactNode } from "react";
import { ChatHistory } from "@/components/ChatHistory";
import { SidebarLeftIcon, SidebarRightIcon } from "@/components/icons";
import { ThemeToggle } from "@/components/ThemeToggle";
import { TodayPanel } from "@/components/TodayPanel";
import { WaitingBadge } from "@/components/approvals/WaitingBadge";
import { setHidden, useHidden } from "@/lib/layoutPrefs";

const NAV = [
  { href: "/", label: "Chat", icon: "💬" },
  { href: "/approvals", label: "Approvals", icon: "✅" },
  { href: "/social", label: "Social", icon: "📣" },
  { href: "/freelance", label: "Freelance", icon: "💼" },
  { href: "/news", label: "News", icon: "📰" },
  { href: "/profile", label: "Profile", icon: "👤" },
  { href: "/memory", label: "Memory", icon: "🧠" },
  { href: "/activity", label: "Activity", icon: "📜" },
  { href: "/settings", label: "Settings", icon: "⚙" },
];

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
  const leftOpen = openDrawer?.side === "left" && openDrawer.path === pathname;
  const rightOpen = openDrawer?.side === "right" && openDrawer.path === pathname;
  const setLeftOpen = (open: boolean) => setOpenDrawer(open ? { side: "left", path: pathname } : null);
  const setRightOpen = (open: boolean) =>
    setOpenDrawer(open ? { side: "right", path: pathname } : null);

  const docked = (query: string) => window.matchMedia(query).matches;
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
        <div className="flex items-center justify-between gap-1 px-4 pt-4 pb-3">
          <Link href="/" className="mr-auto font-semibold tracking-tight">
            Junior Muneer
          </Link>
          <ThemeToggle />
          <button onClick={hideLeft} className={iconButton} aria-label="Hide sidebar" title="Hide sidebar">
            <SidebarLeftIcon className="h-[18px] w-[18px]" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-2">
          <Suspense>
            <ChatHistory />
          </Suspense>
        </div>
        <nav className="border-t border-line p-2">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm ${
                  active ? "bg-accent-soft font-medium text-ink" : "text-muted hover:bg-panel-2"
                }`}
              >
                <span aria-hidden>{item.icon}</span>
                {item.label}
                {item.href === "/approvals" && <WaitingBadge />}
              </Link>
            );
          })}
        </nav>
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
