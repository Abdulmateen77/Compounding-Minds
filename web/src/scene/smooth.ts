/** Critically damped spring (the SmoothDamp form): follows a moving target with no overshoot and a continuous velocity, so a target
    that jumps (a new speaker, a state change, a scrub) becomes a glide instead of a snap. `time` is roughly how long it takes to settle. */
export class Spring {
  x: number;
  v = 0;
  private primed = false;
  constructor(x = 0) { this.x = x; }

  /** Move toward `target`. The first call lands on it, so nothing sweeps in from the initial value. */
  to(target: number, time: number, dt: number): number {
    if (!this.primed) { this.primed = true; this.x = target; this.v = 0; return this.x; }
    const w = 2 / Math.max(0.0001, time), a = w * dt;
    const k = 1 / (1 + a + 0.48 * a * a + 0.235 * a * a * a);
    const d = this.x - target, tmp = (this.v + w * d) * dt;
    this.v = (this.v - w * tmp) * k;
    this.x = target + (d + tmp) * k;
    return this.x;
  }
}

/** Frame time for animation: real seconds, capped so a stalled tab does not fling anything on return. */
export const frameDt = (dt: number) => Math.min(0.05, Math.max(0, dt));
