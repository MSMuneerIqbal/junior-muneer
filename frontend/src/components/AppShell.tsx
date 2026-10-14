"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useState, type ReactNode } from "react";
import { ChatHistory } from "@/components/ChatHistory";
import { ThemeToggle } from "@/components/ThemeToggle";
import { TodayPanel } from "@/components/TodayPanel";

const NAV = [
  { href: "/", label: "Chat", icon: "💬" },
  { href: "/memory", label: "Memory", icon: "🧠" },
  { href: "/activity", label: "Activity", icon: "📜" },
  { href: "/settings", label: "Settings", icon: "⚙" },
];

/** Three columns: sidebar · main · Today panel. On a phone the side panels become drawers. */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  // A drawer stays open only on the page where it was opened, so navigating closes it.
  const [openDrawer, setOpenDrawer] = useState<{ side: "left" | "right"; path: string } | null>(
    null,
  );
  const leftOpen = openDrawer?.side === "left" && openDrawer.path === pathname;
  const rightOpen = openDrawer?.side === "right" && openDrawer.path === pathname;
  const setLeftOpen = (open: boolean) => setOpenDrawer(open ? { side: "left", path: pathname } : null);
  const setRightOpen = (open: boolean) =>
    setOpenDrawer(open ? { side: "right", path: pathname } : null);

  return (
    <div className="flex h-dvh overflow-hidden">
      {(leftOpen || rightOpen) && (
        <button
          aria-label="Close panel"
          className="fixed inset-0 z-30 bg-black/30 lg:hidden"
          onClick={() => {
            setLeftOpen(false);
            setRightOpen(false);
          }}
        />
      )}

      <aside
        onClick={(e) => {
          // Picking a chat or page closes the drawer on phones.
          if ((e.target as HTMLElement).closest("a")) setLeftOpen(false);
        }}
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-line bg-panel transition-transform lg:static lg:translate-x-0 ${
          leftOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-4 pt-4 pb-3">
          <Link href="/" className="font-semibold tracking-tight">
            Junior Muneer
          </Link>
          <ThemeToggle />
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
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-line bg-panel px-3 py-2 lg:hidden">
          <button
            className="rounded-md px-2 py-1 text-lg"
            aria-label="Open chats and menu"
            onClick={() => setLeftOpen(true)}
          >
            ☰
          </button>
          <span className="font-semibold">Junior Muneer</span>
          <button
            className="rounded-md px-2 py-1 text-sm"
            aria-label="Open today panel"
            onClick={() => setRightOpen(true)}
          >
            Today
          </button>
        </header>
        <main className="min-h-0 flex-1">{children}</main>
      </div>

      <aside
        className={`fixed inset-y-0 right-0 z-40 w-72 border-l border-line bg-panel transition-transform xl:static xl:translate-x-0 ${
          rightOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <TodayPanel />
      </aside>
    </div>
  );
}
