import type { Check, Lens } from "../research";
import { THINK_LEAD, THINK_TAIL } from "./timeline";

/* Pure helpers shared by the 3D scene and the 2D fallback (no three.js here, so the fallback never loads it). Everything the
   investors "say" in the panel comes from the report: their checks (what was asked, what was found, the idea behind it) and the
   written view the model produced from those checks. The only thing decided here is how long each takes to appear. */

export type Stance = "for" | "neutral" | "against";
export const stanceOf = (fit: number | null): Stance => (fit == null ? "neutral" : fit >= 0.7 ? "for" : fit >= 0.4 ? "neutral" : "against");
export const counts = (l: Lens) => ({ pass: l.checks.filter((c) => c.result === "pass").length, known: l.checks.filter((c) => c.result !== "unknown").length });
export const cut = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);
export const checkLabel = (k: Check) => k.check.split(":")[0].trim();
export const surname = (l: Lens) => l.name.trim().split(/\s+/).slice(-1)[0];

export const MARK: Record<Check["result"], { mark: string; color: string }> = {
  pass: { mark: "✓", color: "var(--success)" },
  partial: { mark: "~", color: "var(--warning)" },
  fail: { mark: "✗", color: "var(--error)" },
  unknown: { mark: "?", color: "var(--muted)" },
};
export const RESULT_WORD: Record<Check["result"], string> = { pass: "passes", partial: "partly passes", fail: "fails", unknown: "could not be tested" };

/* ---- pacing: how long each thing takes ------------------------------------------------------------------------------------- */
export const SECONDS_PER_CHECK = 1.25;     // one check: read the question, look at the figure, settle on a result
export const thinkSeconds = (l: Lens) => THINK_LEAD + THINK_TAIL + SECONDS_PER_CHECK * Math.max(1, l.checks.length);
export const READ_CHARS_PER_SECOND = 60;
export const speakSeconds = (text: string) => 1.6 + Math.min(text.length, 280) / READ_CHARS_PER_SECOND;

/** The investor's reading in their own words: the first two sentences of the written view (up to 280 characters), else their
    first testable check. This is what is typed out when they give their reading. */
export function readingOf(l: Lens): string {
  const text = l.narrative?.trim();
  if (text) {
    // lazy up to a stop followed by space, so "1.5 times" stays inside its sentence instead of losing the words before it
    const s = text.match(/[\s\S]+?[.!?]+(?=\s|$)/g) ?? [text];
    let out = "";
    for (const sent of s) { if ((out + sent).length > 280 && out) break; out = `${out}${sent}`.trimStart() + " "; if (out.length > 160) break; }
    return cut(out.trim(), 280);
  }
  const k = l.checks.find((c) => c.result !== "unknown");
  return k ? `${checkLabel(k)}: ${k.shown}` : l.question;
}

/** Characters of `text` revealed `seconds` after it started, at a reading-friendly typing speed. */
export const typed = (text: string, seconds: number, cps = 70) => text.slice(0, Math.max(0, Math.floor(seconds * cps)));

/* ---- face-offs ------------------------------------------------------------------------------------------------------------- */
export type Quote = { mark: string; color: string; head: string; shown: string; idea: string };
/** One turn in a face-off. `to` is who it is addressed to. A "ruling" is the judge's: `headline` is the verdict itself and `quote` is
    one of the judge's own checks that it rests on. */
export type FaceTurn = { by: number; to: number; role: "case" | "objection" | "ruling"; quote: Quote; headline?: string };
/** `judge.winner` is the investor the judge sides with, or null for a split decision. */
export type FaceOff = { pair: [number, number]; turns: FaceTurn[]; judge?: { by: number; winner: number | null } };
export const SPLIT_BAND = 0.04;           // if the judge is this close to equally far from both sides, it is a split decision
const PRICEY = /price|earn|book|valu|multiple|margin of safety/i;
export const FACEOFF_GAP = 0.3;            // how far apart two investors' fits must be to argue
export const MAX_FACEOFFS = 3;

const quoteOf = (k: Check): Quote => ({ mark: MARK[k.result].mark, color: MARK[k.result].color, head: cut(checkLabel(k), 60), shown: cut(k.shown, 96), idea: cut(k.principle, 110) });
/** How long one turn of a face-off takes to say; a ruling gets a beat longer, for the verdict to land. */
export const turnSeconds = (q: Quote) => 1.1 + (q.head.length + q.shown.length) / 45;
export const faceTurnSeconds = (t: FaceTurn) => turnSeconds(t.quote) + (t.role === "ruling" ? 1.8 : 0);

/** The judge for a face-off: someone who was not arguing and whose own reading sits closest to the middle of the two, so they come
    to it as neutral as the panel allows. Judges already used in another face-off are passed over if anyone else will do. */
function pickJudge(lenses: Lens[], hi: number, lo: number, taken: Set<number>): number {
  const mid = ((lenses[hi].fit as number) + (lenses[lo].fit as number)) / 2;
  const ok = lenses.map((l, i) => i).filter((i) => i !== hi && i !== lo && lenses[i].fit != null && lenses[i].checks.some((k) => k.result !== "unknown"));
  ok.sort((a, b) => Number(taken.has(a)) - Number(taken.has(b)) || Math.abs((lenses[a].fit as number) - mid) - Math.abs((lenses[b].fit as number) - mid));
  return ok[0] ?? -1;
}

/** The ruling: the judge sides with whichever of the two is nearer their own reading (a split if it is a near tie), and says why in
    terms of one of their own checks: a passed one if they side with the case, a failed one (price first) if with the objection. */
function ruling(lenses: Lens[], judge: number, hi: number, lo: number): { turn: FaceTurn; winner: number | null } | null {
  const J = lenses[judge], jf = J.fit as number;
  const dHi = Math.abs(jf - (lenses[hi].fit as number)), dLo = Math.abs(jf - (lenses[lo].fit as number));
  const winner = Math.abs(dHi - dLo) < SPLIT_BAND ? null : dHi < dLo ? hi : lo;
  const known = J.checks.filter((k) => k.result !== "unknown");
  const price = (a: Check, b: Check) => Number(PRICEY.test(b.check)) - Number(PRICEY.test(a.check));
  const check = (winner === hi ? known.find((k) => k.result === "pass")
    : winner === lo ? known.filter((k) => k.result === "fail").sort(price)[0]
    : known.find((k) => k.result === "partial") ?? known[0]) ?? known[0];
  if (!check) return null;
  const headline = winner == null ? "A split decision: both of them have a point." : `I side with ${surname(lenses[winner])}.`;
  return { winner, turn: { by: judge, to: winner ?? hi, role: "ruling", quote: quoteOf(check), headline } };
}

/** The investors who disagree, paired up: the biggest gap in fit first, nobody in two face-offs, and only where there is
    something real to say on both sides (a passed check for one, a failed one for the other). Can be none, one, or several. */
export function pickFaceOffs(lenses: Lens[]): FaceOff[] {
  const cands: { hi: number; lo: number; gap: number }[] = [];
  lenses.forEach((a, i) => lenses.forEach((b, j) => {
    if (i >= j || a.fit == null || b.fit == null) return;
    const gap = Math.abs(a.fit - b.fit);
    if (gap >= FACEOFF_GAP) cands.push(a.fit > b.fit ? { hi: i, lo: j, gap } : { hi: j, lo: i, gap });
  }));
  cands.sort((x, y) => y.gap - x.gap);
  const used = new Set<number>(), judges = new Set<number>(), out: FaceOff[] = [];
  for (const c of cands) {
    if (used.has(c.hi) || used.has(c.lo)) continue;
    const cases = lenses[c.hi].checks.filter((k) => k.result === "pass");
    const objections = lenses[c.lo].checks.filter((k) => k.result === "fail").sort((x, y) => Number(PRICEY.test(y.check)) - Number(PRICEY.test(x.check)));
    if (!cases.length || !objections.length) continue;
    const turns: FaceTurn[] = [];
    for (let r = 0; r < 2; r++) {
      if (cases[r]) turns.push({ by: c.hi, to: c.lo, role: "case", quote: quoteOf(cases[r]) });
      if (objections[r]) turns.push({ by: c.lo, to: c.hi, role: "objection", quote: quoteOf(objections[r]) });
    }
    const jd = pickJudge(lenses, c.hi, c.lo, judges), rule = jd >= 0 ? ruling(lenses, jd, c.hi, c.lo) : null;
    if (rule) { turns.push(rule.turn); judges.add(jd); }
    out.push({ pair: [c.hi, c.lo], turns, judge: rule ? { by: jd, winner: rule.winner } : undefined });
    used.add(c.hi); used.add(c.lo);
    if (out.length >= MAX_FACEOFFS) break;
  }
  return out;
}
