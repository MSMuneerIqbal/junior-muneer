"use client";

import { useWaitingCount } from "@/lib/approvals";

/** How many drafts wait for you, next to "Approvals" in the menu. */
export function WaitingBadge() {
  const waiting = useWaitingCount();
  if (!waiting) return null;
  return (
    <span
      aria-label={`${waiting} waiting`}
      className="ml-auto rounded-full bg-accent px-1.5 text-[11px] font-semibold leading-5 text-accent-fg tabular-nums"
    >
      {waiting}
    </span>
  );
}
