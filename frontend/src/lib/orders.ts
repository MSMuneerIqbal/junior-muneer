/** Fiverr orders (P5-08): how long until one is due, and how urgent that looks. */

const HOUR = 3_600_000;

export function timeLeft(dueIso: string, now: number): { text: string; tone: string } {
  const ms = Date.parse(dueIso) - now;
  const mins = Math.round(Math.abs(ms) / 60_000);
  const span = mins < 60 ? `${mins} min` : mins < 48 * 60 ? `${Math.floor(mins / 60)} h` : `${Math.floor(mins / 1440)} days`;
  if (ms < 0) return { text: `late by ${span}`, tone: "font-medium text-danger" };
  if (ms <= 6 * HOUR) return { text: `in ${span}`, tone: "font-medium text-danger" };
  if (ms <= 24 * HOUR) return { text: `in ${span}`, tone: "text-warn" };
  return { text: `in ${span}`, tone: "text-muted" };
}
