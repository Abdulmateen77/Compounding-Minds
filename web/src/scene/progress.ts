/** Where the reader got to in the investor panel's prologue, per company, so leaving the tab and coming back (or reloading) picks up
    where they were instead of starting over. Kept for this browser tab only. Storage can be blocked, so the in-memory copy always
    works and every storage call is guarded. `done` means they have watched all the way through at least once. */
export type Progress = { clock: number; done: boolean };

const mem = new Map<string, Progress>();
const key = (cik: number | string, sig: string) => `cm.prologue.${cik}.${sig}`;

export function loadProgress(cik: number | string, sig: string): Progress | null {
  const k = key(cik, sig);
  const hit = mem.get(k);
  if (hit) return hit;
  try {
    const p = JSON.parse(window.sessionStorage.getItem(k) ?? "null") as Progress | null;
    if (p && Number.isFinite(p.clock)) { mem.set(k, p); return p; }
  } catch { /* nothing saved */ }
  return null;
}

export function saveProgress(cik: number | string, sig: string, p: Progress) {
  const k = key(cik, sig);
  mem.set(k, p);
  try { window.sessionStorage.setItem(k, JSON.stringify(p)); } catch { /* the in-memory copy still serves this visit */ }
}
