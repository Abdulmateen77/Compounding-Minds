/** The company the reader just picked in a search, kept for this tab only so the loading room can say its name while the
    report is being built (the report itself is what carries the name afterwards). Storage can be blocked: everything is guarded. */
export type Picked = { cik: number; name: string; ticker: string | null };
const KEY = "cm.picked";
const RECENT_KEY = "cm.recent.v1";
const RECENT_MAX = 5;

export function rememberPicked(p: Picked) {
  try { window.sessionStorage.setItem(KEY, JSON.stringify(p)); } catch { /* the room just shows a generic title */ }
  try {
    const rest = recallRecent().filter((r) => r.cik !== p.cik);
    window.localStorage.setItem(RECENT_KEY, JSON.stringify([p, ...rest].slice(0, RECENT_MAX)));
  } catch { /* the recent list is a convenience, losing it is fine */ }
}

export function recallPicked(cik: number | string): Picked | null {
  try {
    const p = JSON.parse(window.sessionStorage.getItem(KEY) ?? "null") as Picked | null;
    return p && String(p.cik) === String(cik) ? p : null;
  } catch { return null; }
}

/** The last few companies searched for in this browser, newest first. */
export function recallRecent(): Picked[] {
  try {
    const list = JSON.parse(window.localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(list) ? list.filter((p): p is Picked => p && typeof p.cik === "number" && typeof p.name === "string").slice(0, RECENT_MAX) : [];
  } catch { return []; }
}
