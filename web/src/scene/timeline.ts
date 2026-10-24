// Pure timeline for the scene. Times are seconds at 1x on the director clock.
//
// Two shapes share it. The assessment replay (LiveScene) gives every analyst the same short window. The investor panel
// (ResearchScene) gives each investor a research window as long as their own work (one slot per check) followed by a reading
// as long as their own text, and any number of face-offs, each as long as what is said in it.

export type Turn = { start: number; end: number };
export type DebateWindow = { start: number; end: number; turns: Turn[] };

export type Timeline = {
  n: number;
  ingest: [number, number];
  metrics: [number, number];
  committee: [number, number];
  speak: number[];      // when each agent's reading begins
  speakLen: number[];   // how long each agent's reading lasts
  thinkLen: number[];   // each agent's research window; it ends where their reading begins (0 = none)
  cross: [number, number] | null;   // from the start of the first face-off to the end of the last
  debates: DebateWindow[];          // each face-off. Empty with a non-null `cross` means the old "everyone looks at everyone" beat
  synth: [number, number];
  stamp: number;
  end: number;
};

export type Phase = "ingest" | "metrics" | "committee" | "cross_exam" | "synthesis" | "done";

const D = { ingest: 2.4, metrics: 2.6, lead: 1.2, speak: 3.2, tail: 0.5, cross: 2.6, synth: 3.8, hold: 2.4, faceLead: 0.9, faceTail: 0.6 };

/** Time an investor spends before their first check and after their last, inside their research window. */
export const THINK_LEAD = 0.5, THINK_TAIL = 0.4;
/** The part of one check's slot after which the check counts as done (the rest is the result settling). */
const DONE_AT = 0.8;

export type TimelineOpts = {
  speak?: number | number[];      // per agent reading length (or one length for all)
  think?: number | number[];      // per agent research length
  cross?: number;                 // length of the old everyone-looks-at-everyone beat
  debates?: number[][];           // one entry per face-off: the length of each turn in it
};

export function buildTimeline(n: number, hasCross: boolean, opts: TimelineOpts = {}): Timeline {
  const pick = (v: number | number[] | undefined, i: number, d: number) => (Array.isArray(v) ? (v[i] ?? d) : (v ?? d));
  const thinkLen = Array.from({ length: n }, (_, i) => pick(opts.think, i, 0));
  const speakLen = Array.from({ length: n }, (_, i) => pick(opts.speak, i, D.speak));
  const ingest: [number, number] = [0, D.ingest];
  const metrics: [number, number] = [ingest[1], ingest[1] + D.metrics];
  const c0 = metrics[1];

  let cur = c0 + D.lead;
  const speak: number[] = [];
  for (let i = 0; i < n; i++) { cur += thinkLen[i]; speak.push(cur); cur += speakLen[i]; }
  const c1 = cur + D.tail;

  const debates: DebateWindow[] = [];
  let cross: [number, number] | null = null;
  if (opts.debates?.length) {
    let at = c1;
    for (const lens of opts.debates) {
      let t = at + D.faceLead;
      const turns = lens.map((len) => { const s = t; t += len; return { start: s, end: t }; });
      debates.push({ start: at, end: t + D.faceTail, turns });
      at = t + D.faceTail;
    }
    cross = [c1, at];
  } else if (hasCross) {
    cross = [c1, c1 + (opts.cross ?? D.cross)];
  }
  const s0 = cross ? cross[1] : c1;
  const synth: [number, number] = [s0, s0 + D.synth];
  return { n, ingest, metrics, committee: [c0, c1], speak, speakLen, thinkLen, cross, debates, synth, stamp: s0 + 2.0, end: synth[1] + D.hold };
}

export function phaseAt(tl: Timeline, t: number): Phase {
  if (t < tl.ingest[1]) return "ingest";
  if (t < tl.metrics[1]) return "metrics";
  if (t < tl.committee[1]) return "committee";
  if (tl.cross && t < tl.cross[1]) return "cross_exam";
  if (t < tl.synth[1]) return "synthesis";
  return "done";
}

export type AgentState = "idle" | "thinking" | "speaking" | "done";
export function agentState(tl: Timeline, i: number, t: number): AgentState {
  if (t < tl.committee[0]) return "idle";
  if (t < tl.speak[i]) return "thinking";
  if (t < tl.speak[i] + tl.speakLen[i]) return "speaking";
  return "done";
}

/** 0..1 progress through agent i's research window, or null when they are not in it. */
export function thinkProgress(tl: Timeline, i: number, t: number): number | null {
  const len = tl.thinkLen[i];
  if (len <= 0) return null;
  const a = tl.speak[i] - len;
  return t >= a && t < tl.speak[i] ? (t - a) / len : null;
}

/** When agent i's m checks run: the first starts at `start` and each takes `slot` seconds. Null if they have no research window. */
export type CheckPlan = { start: number; slot: number };
export function checkPlan(tl: Timeline, i: number, m: number): CheckPlan | null {
  const len = tl.thinkLen[i];
  if (len <= 0 || m <= 0) return null;
  return { start: tl.speak[i] - len + THINK_LEAD, slot: (len - THINK_LEAD - THINK_TAIL) / m };
}
/** The moment check k counts as finished. */
export const checkDoneAt = (p: CheckPlan, k: number) => p.start + (k + DONE_AT) * p.slot;

/** How far through their checks agent i is: how many are finished, which one is under way, and how far into it. */
export function checkState(tl: Timeline, i: number, t: number, m: number): { done: number; current: number | null; phase: number } | null {
  const p = checkPlan(tl, i, m);
  if (!p) return null;
  const x = (t - p.start) / p.slot;
  if (x < 0) return { done: 0, current: null, phase: 0 };
  if (x >= m) return { done: m, current: null, phase: 1 };
  const k = Math.floor(x), phase = x - k;
  return { done: k + (phase >= DONE_AT ? 1 : 0), current: k, phase };
}
