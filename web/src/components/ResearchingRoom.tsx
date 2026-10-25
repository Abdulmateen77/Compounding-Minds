import { Component, lazy, Suspense, useEffect, useMemo, useState, type ReactNode } from "react";
import { RESEARCH_STEPS, STEP_SECONDS } from "../research";
import { recallPicked } from "../recent";
import { demoMode, useReducedMotion } from "../route";
import { hasWebGL } from "../scene/support";

const ResearchingScene = lazy(() => import("../scene/ResearchingScene"));

class Boundary extends Component<{ onError: () => void; children: ReactNode }, { bad: boolean }> {
  state = { bad: false };
  static getDerivedStateFromError() { return { bad: true }; }
  componentDidCatch(e: unknown) { console.warn("research room failed; the plain loading card takes over", e); this.props.onError(); }
  render() { return this.state.bad ? null : this.props.children; }
}

/** What the Investor panel shows while the report is built: the investors researching in their room, with the four steps and the
    time so far. Falls back to `plain` (the ordinary loading card) when 3D is unavailable or motion is reduced. */
export function ResearchingRoom({ cik, plain }: { cik: string; plain: (name?: string) => ReactNode }) {
  const reduced = useReducedMotion();
  const webgl = useMemo(hasWebGL, []);
  const [failed, setFailed] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const picked = useMemo(() => recallPicked(cik), [cik]);
  const presenting = useMemo(demoMode, []);

  useEffect(() => { const t = setInterval(() => setSeconds((s) => s + 1), 1000); return () => clearInterval(t); }, []);
  const step = Math.min(Math.floor(seconds / STEP_SECONDS), RESEARCH_STEPS.length - 1);
  const name = picked?.name;

  if (reduced || !webgl || failed) return <>{plain(name)}</>;

  const room = (
    <Boundary onError={() => setFailed(true)}>
      <Suspense fallback={<div className="card grid place-items-center mute text-sm" style={{ aspectRatio: "16 / 9", minHeight: 380, width: "100%" }} role="status">Setting up the office…</div>}>
        <ResearchingScene name={name} step={step} seconds={seconds} onFail={() => setFailed(true)} demo={presenting} />
      </Suspense>
    </Boundary>
  );
  if (presenting) return <div className="fixed inset-0 z-[var(--z-modal)] grid place-items-center" style={{ background: "#05070d" }}>{room}</div>;
  return (
    <section className="grid gap-3" aria-label="Investor panel">
      <h2 className="text-xl font-semibold m-0">Investor panel: researching {name ?? "the company"}</h2>
      {room}
    </section>
  );
}
