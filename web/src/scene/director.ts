import { useSyncExternalStore } from "react";
import { buildTimeline, type Timeline, type TimelineOpts } from "./timeline";

/** What the stream has delivered so far; the clock never runs past what has arrived (unless the stream is finished or failed). */
export type Inputs = { calls: number; verdict: boolean; done: boolean; failed: boolean };

/** Playback clock for the scene. Owned outside the canvas so DOM overlays, controls and WebGL share one source of truth. */
export class Director {
  clock = 0;
  playing = true;
  speed = 1;
  tl: Timeline;
  inputs: Inputs = { calls: 0, verdict: false, done: false, failed: false };
  private version = 0;
  private listeners = new Set<() => void>();
  private raf = 0;
  private last = 0;
  private lastEmit = 0;
  private visible = true;

  /** The face-offs, in order: who faces whom, and who makes each turn (one entry per turn in the timeline). Empty means the old
      cross-examination beat, where everyone looks at everyone. */
  faceoffs: { pair: [number, number]; by: number[]; to: number[]; judge?: number }[] = [];
  /** Where the viewer was when they last left (restored progress), or null. Set by the scene, which owns the saving. */
  resumedAt: number | null = null;
  /** The viewer had already watched everything through once. */
  wasDone = false;
  /** The desk the viewer is talking to: the camera leans toward them and they face the viewer. */
  spot: number | null = null;
  /** That investor is composing an answer (thinking dots). */
  busy = false;
  /** performance.now() when their last answer arrived, for a small hop. */
  replyAt = -1e9;
  /** The report is still being built: the investors read and type, and filings are handed out from the table. */
  researching = false;

  constructor(n: number, hasCross: boolean, opts?: TimelineOpts) { this.tl = buildTimeline(n, hasCross, opts); }

  /** The face-off under way at `t`, if any. */
  activeDebate(t = this.clock): { k: number; pair: [number, number]; start: number; end: number } | null {
    const ds = this.tl.debates;
    for (let k = 0; k < ds.length; k++) if (t >= ds[k].start && t < ds[k].end && this.faceoffs[k]) return { k, pair: this.faceoffs[k].pair, start: ds[k].start, end: ds[k].end };
    return null;
  }
  /** Who is making their point at `t` in the face-off under way, who is listening, and how far into the turn we are. */
  speakerAt(t = this.clock): { who: number; other: number; k: number; turn: number; u: number; judge: boolean } | null {
    const d = this.activeDebate(t);
    if (!d) return null;
    const turns = this.tl.debates[d.k].turns, j = turns.findIndex((x) => t >= x.start && t < x.end);
    const who = this.faceoffs[d.k].by[j];
    if (j < 0 || who == null) return null;
    const fo = this.faceoffs[d.k];
    return { who, other: fo.to[j] ?? (who === d.pair[0] ? d.pair[1] : d.pair[0]), k: d.k, turn: j, u: (t - turns[j].start) / (turns[j].end - turns[j].start), judge: fo.judge === who };
  }

  subscribe = (l: () => void) => { this.listeners.add(l); return () => this.listeners.delete(l); };
  getVersion = () => this.version;
  private emit() { this.version++; this.listeners.forEach((l) => l()); }

  /** Highest clock value currently allowed by the data that has arrived. */
  cap(): number {
    const { tl, inputs: i } = this;
    if (i.done || i.failed) return tl.end;
    if (i.calls < tl.n) return tl.speak[i.calls];
    if (!i.verdict) return tl.stamp;
    return tl.end;
  }
  get finished() { return this.clock >= this.tl.end - 0.001; }
  get waiting() { return this.playing && !this.finished && this.clock >= this.cap() - 0.001; }

  start() {
    this.last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(0.1, (now - this.last) / 1000);
      this.last = now;
      if (this.playing && this.visible) this.clock = Math.min(this.clock + dt * this.speed, this.cap(), this.tl.end);
      if (now - this.lastEmit > 50) { this.lastEmit = now; this.emit(); }   // fast enough for text to type smoothly
      this.raf = requestAnimationFrame(loop);
    };
    this.raf = requestAnimationFrame(loop);
  }
  stop() { cancelAnimationFrame(this.raf); }

  setPlaying(p: boolean) { this.playing = p; this.emit(); }
  setSpeed(s: number) { this.speed = s; this.emit(); }
  replay() { this.clock = 0; this.playing = true; this.emit(); }
  seek(t: number) { this.clock = Math.min(t, this.tl.end); this.emit(); }
}

export function useDirectorTick(d: Director) {
  return useSyncExternalStore(d.subscribe, d.getVersion);
}
