// Pure timeline for the live scene. Times are seconds at 1x on the director clock.
export type Timeline = {
  n: number;
  ingest: [number, number];
  metrics: [number, number];
  committee: [number, number];
  speak: number[];      // start of each agent's speaking window
  speakDur: number;
  cross: [number, number] | null;
  synth: [number, number];
  stamp: number;
  end: number;
};

export type Phase = "ingest" | "metrics" | "committee" | "cross_exam" | "synthesis" | "done";

const D = { ingest: 2.4, metrics: 2.6, lead: 1.2, speak: 3.2, tail: 0.5, cross: 2.6, synth: 3.8, hold: 2.4 };

export function buildTimeline(n: number, hasCross: boolean): Timeline {
  const ingest: [number, number] = [0, D.ingest];
  const metrics: [number, number] = [ingest[1], ingest[1] + D.metrics];
  const c0 = metrics[1];
  const speak = Array.from({ length: n }, (_, i) => c0 + D.lead + i * D.speak);
  const c1 = c0 + D.lead + n * D.speak + D.tail;
  const cross: [number, number] | null = hasCross ? [c1, c1 + D.cross] : null;
  const s0 = cross ? cross[1] : c1;
  const synth: [number, number] = [s0, s0 + D.synth];
  return { n, ingest, metrics, committee: [c0, c1], speak, speakDur: D.speak, cross, synth, stamp: s0 + 2.0, end: synth[1] + D.hold };
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
  if (t < tl.speak[i] + tl.speakDur) return "speaking";
  return "done";
}
