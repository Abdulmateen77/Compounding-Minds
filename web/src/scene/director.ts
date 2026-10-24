import { useSyncExternalStore } from "react";
import { buildTimeline, type Timeline } from "./timeline";

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

  constructor(n: number, hasCross: boolean) { this.tl = buildTimeline(n, hasCross); }

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
      if (now - this.lastEmit > 100) { this.lastEmit = now; this.emit(); }
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
