/** The company the reader just picked in a search, kept for this tab only so the loading room can say its name while the
    report is being built (the report itself is what carries the name afterwards). Storage can be blocked: everything is guarded. */
type Picked = { cik: number; name: string; ticker: string | null };
const KEY = "cm.picked";

export function rememberPicked(p: Picked) {
  try { window.sessionStorage.setItem(KEY, JSON.stringify(p)); } catch { /* the room just shows a generic title */ }
}

export function recallPicked(cik: number | string): Picked | null {
  try {
    const p = JSON.parse(window.sessionStorage.getItem(KEY) ?? "null") as Picked | null;
    return p && String(p.cik) === String(cik) ? p : null;
  } catch { return null; }
}
