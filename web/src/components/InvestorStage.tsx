import { Component, lazy, Suspense, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { fmtValue, type Report } from "../research";
import { demoMode, useReducedMotion } from "../route";
import { hasWebGL } from "../scene/support";
import type { Speech } from "./DebateLog";

// three + react-three-fiber are their own chunk: nothing about the 3D is downloaded until someone asks to watch it.
const ResearchScene = lazy(() => import("../scene/ResearchScene"));

class SceneBoundary extends Component<{ onError: (why: string) => void; children: ReactNode }, { bad: boolean }> {
  state = { bad: false };
  static getDerivedStateFromError() { return { bad: true }; }
  componentDidCatch(e: unknown) { console.warn("investor scene failed; the written debate stands in", e); this.props.onError(String((e as Error)?.message ?? e)); }
  render() { return this.state.bad ? null : this.props.children; }
}

/** The debate staged in the 3D office: the investors work through their checks, give their readings, and the ones who disagree
    argue it out. Optional: the page works without it, and nothing in it locks anything. Presenter mode (`?demo=1`, or the Present
    button) fills the window and loops. When the scene cannot or should not run (reduced motion, no WebGL, an error) a short note
    says so, and the written debate beside it covers the same ground. */
export function InvestorStage({ r, fromLoading = false, speech = null, onPick }: { r: Report; fromLoading?: boolean; speech?: Speech | null; onPick?: (i: number) => void }) {
  const reduced = useReducedMotion();
  const [failed, setFailed] = useState(false);
  const [playAnyway, setPlayAnyway] = useState(false);
  const [presenting, setPresenting] = useState(demoMode);
  const webgl = useMemo(hasWebGL, []);
  const a = r.analysis;

  const cards = useMemo(() => (r.scorecard ?? []).slice(0, 6).map((f) => ({ name: f.label, value: fmtValue(f.unit, f.value) })), [r.scorecard]);

  const present = () => {
    setPresenting(true);
    try { void document.documentElement.requestFullscreen?.(); } catch { /* the overlay already fills the window */ }
  };
  const exit = useCallback(() => {
    setPresenting(false);
    try {
      const u = new URL(window.location.href);
      u.searchParams.delete("demo");
      u.hash = u.hash.replace(/[?&]demo=1/, "");
      window.history.replaceState(null, "", u);
      if (document.fullscreenElement) void document.exitFullscreen();
    } catch { /* leaving the flag in the address bar is harmless */ }
  }, []);

  useEffect(() => {
    if (!presenting) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [presenting]);

  if (!a || a.lenses.length === 0) return null;
  const c = r.company;
  const motionOk = webgl && !failed && (!reduced || playAnyway);

  if (!motionOk) {
    const why = failed ? "The 3D view could not start on this device." : !webgl ? "This device can't draw the 3D view." : "The 3D view is off because your device asks for reduced motion.";
    return (
      <div className="card p-4 flex items-center justify-between gap-3 flex-wrap">
        <p className="m-0 text-sm">{why} <span className="mute">The written debate says the same thing.</span></p>
        {reduced && webgl && !failed && <button className="btn ghost" onClick={() => setPlayAnyway(true)}>Show the 3D view anyway</button>}
      </div>
    );
  }

  const scene = (demo: boolean) => (
    <SceneBoundary onError={() => setFailed(true)}>
      <Suspense fallback={<div className="grid place-items-center mute text-sm" style={{ aspectRatio: "16 / 9", minHeight: 380, width: "100%" }} role="status">Setting up the office…</div>}>
        <ResearchScene
          cik={c.cik} name={c.name} sub={[c.ticker, c.exchange].filter(Boolean).join(" · ")} asOf={r.as_of ?? r.data_through ?? ""}
          lenses={a.lenses} cards={cards} overall={a.overall} onFail={() => setFailed(true)} demo={demo} onExitDemo={exit} fromLoading={fromLoading}
          debates speech={speech} onPick={onPick} />
      </Suspense>
    </SceneBoundary>
  );

  if (presenting) {
    return (
      <div className="fixed inset-0 z-[var(--z-modal)] grid place-items-center" style={{ background: "#05070d" }} role="dialog" aria-label="Presenter mode">
        {scene(true)}
        <button className="btn ghost absolute right-3 top-3" onClick={exit} aria-label="Exit presenter mode">Exit (X)</button>
      </div>
    );
  }

  return (
    <div className="grid gap-3 grid-cols-[minmax(0,1fr)]">
      <div className="flex justify-end"><button className="btn ghost sm" onClick={present} title="Full-screen, for showing to a room">Present</button></div>
      {scene(false)}
    </div>
  );
}
