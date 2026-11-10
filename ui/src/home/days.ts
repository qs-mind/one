// Days left to a submission date, counted from the screen's own clock (contract rule 5), and the greeting's part
// of the day.
import { useEffect, useState } from "react";

const DAY_MS = 86_400_000;

/** Whole days from `today` (its local day) to `day` (YYYY-MM-DD): 0 on the day itself, negative once it has passed. */
export function daysUntil(day: string, today: Date): number {
  const [y = 0, m = 1, d = 1] = day.split("-").map(Number);
  return Math.round((Date.UTC(y, m - 1, d) - Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())) / DAY_MS);
}

/** Morning until noon, then evening. */
export const isMorning = (now: Date) => now.getHours() < 12;

/** The screen's clock, moved on at noon and at midnight, so the greeting and every "days left" roll over. */
export function useClock(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const next = new Date(now);
    next.setHours(now.getHours() < 12 ? 12 : 24, 0, 0, 0);
    const timer = setTimeout(() => setNow(new Date()), next.getTime() - now.getTime());
    return () => clearTimeout(timer);
  }, [now]);
  return now;
}
