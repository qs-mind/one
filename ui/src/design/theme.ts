// The colour theme. The core keeps the engineer's choice (a later job wires it); here it lives in memory.
// "system" follows the OS; "light" and "dark" put data-theme on <html>, which tokens.css reads.
import { useSyncExternalStore } from "react";

export type ThemeSetting = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

const DARK_QUERY = "(prefers-color-scheme: dark)";

let setting: ThemeSetting = "system";
const listeners = new Set<() => void>();

const notify = () => {
  for (const listener of listeners) listener();
};

function systemDark(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(DARK_QUERY).matches;
}

export const getThemeSetting = (): ThemeSetting => setting;

export const resolveTheme = (value: ThemeSetting): ResolvedTheme =>
  value === "system" ? (systemDark() ? "dark" : "light") : value;

export function setTheme(next: ThemeSetting): void {
  setting = next;
  if (typeof document !== "undefined") {
    if (next === "system") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", next);
  }
  notify();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  // While the setting is "system", a change of the OS theme changes the resolved theme.
  const media = typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(DARK_QUERY) : null;
  media?.addEventListener("change", listener);
  return () => {
    listeners.delete(listener);
    media?.removeEventListener("change", listener);
  };
}

const snapshot = (): string => `${setting}:${resolveTheme(setting)}`;

export function useTheme(): { setting: ThemeSetting; resolved: ResolvedTheme; setTheme: (next: ThemeSetting) => void } {
  const [current, resolved] = useSyncExternalStore(subscribe, snapshot, snapshot).split(":") as [ThemeSetting, ResolvedTheme];
  return { setting: current, resolved, setTheme };
}
