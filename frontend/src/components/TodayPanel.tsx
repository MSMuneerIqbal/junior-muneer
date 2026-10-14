"use client";

/** Today's spend, Pause, and what needs your OK (filled in P0-17). */
export function TodayPanel() {
  return (
    <div className="flex flex-col gap-3 p-4">
      <h2 className="font-semibold">Today</h2>
      <p className="text-sm text-muted">Spend, Pause and approvals come in P0-17.</p>
    </div>
  );
}
