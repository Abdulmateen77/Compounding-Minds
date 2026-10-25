import { useSyncExternalStore } from "react";
import { asView, type ResearchView } from "./route";

/** What the reader chose at search time: which page a company opens on, and how fast the investor panel plays. Remembered in
    this browser only. Storage can be missing or blocked, so every read and write is guarded and the defaults always work. */
export type Speed = 1 | 1.5 | 2;
export const SPEEDS: Speed[] = [1, 1.5, 2];
export type Level = "beginner" | "intermediate" | "advanced";
export const LEVEL_KEYS: Level[] = ["beginner", "intermediate", "advanced"];
/** `level` is null until the reader has taken the onboarding quiz or skipped it; it decides how much finance jargon the whole site uses. */
export type Prefs = { open: ResearchView; speed: Speed; level: Level | null };

const KEY = "cm.prefs.v1";
const DEFAULTS: Prefs = { open: "overview", speed: 1, level: null };
const listeners = new Set<() => void>();
let cache: Prefs | null = null;

function read(): Prefs {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw) {
      const p = JSON.parse(raw);
      return {
        open: p.open === "investors" || p.open === "report" || p.open === "overview" ? asView(p.open) : DEFAULTS.open,   // "report" was the old long page
        speed: SPEEDS.includes(p.speed) ? p.speed : DEFAULTS.speed,
        level: LEVEL_KEYS.includes(p.level) ? p.level : null,
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
