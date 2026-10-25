import { useSyncExternalStore } from "react";
import type { ResearchView } from "./route";

/** What the reader chose at search time: which page a company opens on, and how fast the investor panel plays. Remembered in
    this browser only. Storage can be missing or blocked, so every read and write is guarded and the defaults always work. */
export type Speed = 1 | 1.5 | 2;
export const SPEEDS: Speed[] = [1, 1.5, 2];
export type Prefs = { open: ResearchView; speed: Speed };

const KEY = "cm.prefs.v1";
const DEFAULTS: Prefs = { open: "report", speed: 1 };
const listeners = new Set<() => void>();
let cache: Prefs | null = null;

function read(): Prefs {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw) {
      const p = JSON.parse(raw);
      return {
        open: p.open === "investors" || p.open === "report" ? p.open : DEFAULTS.open,       // "pro" is now part of the report
        speed: SPEEDS.includes(p.speed) ? p.speed : DEFAULTS.speed,
      };
    }
  } catch { /* fall through to the defaults */ }
  return DEFAULTS;
}

export const getPrefs = (): Prefs => (cache ??= read());

export function setPrefs(p: Partial<Prefs>) {
  cache = { ...getPrefs(), ...p };
  try { window.localStorage.setItem(KEY, JSON.stringify(cache)); } catch { /* the choice still applies for this visit */ }
  listeners.forEach((l) => l());
}

export const usePrefs = (): Prefs => useSyncExternalStore((l) => { listeners.add(l); return () => { listeners.delete(l); }; }, getPrefs);
