import { Component, lazy, Suspense, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import type { ChatMsg } from "../chat";
import { fmtValue, type Report } from "../research";
import { demoMode, useReducedMotion } from "../route";
import InvestorPanel from "../scene/InvestorPanel";
import { pickFaceOffs, surname } from "../scene/lenses";
import { hasWebGL } from "../scene/support";
import { InvestorCards } from "./InvestorCards";
import { InvestorRoster } from "./InvestorRoster";

// three + react-three-fiber are their own chunk, so the rest of the report stays light.
const ResearchScene = lazy(() => import("../scene/ResearchScene"));

class SceneBoundary extends Component<{ onError: (why: string) => void; children: ReactNode }, { bad: boolean }> {
  state = { bad: false };
  static getDerivedStateFromError() { return { bad: true }; }
  componentDidCatch(e: unknown) { console.warn("investor scene failed; the 2D version takes over", e); this.props.onError(String((e as Error)?.message ?? e)); }
  render() { return this.state.bad ? null : this.props.children; }
}

/** The investors, animated: they read the filings, run their checks, give their reading, and the two who disagree most face off;
    you can question any of them. Presenter mode (`?demo=1`, or the Present button) fills the window and loops. When the 3D scene
    cannot or should not run (reduced motion, no WebGL, an error) the same roster, face-off and chat are shown as plain 2D. */
export function InvestorStage({ r, fromLoading = false }: { r: Report; fromLoading?: boolean }) {
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
    return <Plain r={r} why={why} onPlay={reduced && webgl && !failed ? () => setPlayAnyway(true) : undefined} />;
  }

  const scene = (demo: boolean) => (
    <SceneBoundary onError={() => setFailed(true)}>
      <Suspense fallback={<div className="grid place-items-center mute text-sm" style={{ aspectRatio: "16 / 9", minHeight: 380 }} role="status">Setting up the office…</div>}>
        <ResearchScene
          cik={c.cik} name={c.name} sub={[c.ticker, c.exchange].filter(Boolean).join(" · ")} asOf={r.as_of ?? r.data_through ?? ""}
          lenses={a.lenses} cards={cards} overall={a.overall} onFail={() => setFailed(true)} demo={demo} onExitDemo={exit} fromLoading={fromLoading} />
      </Suspense>
    </SceneBoundary>
  );

  if (presenting) {
    return (
      <div className="fixed inset-0 z-50 grid place-items-center" style={{ background: "#05070d" }} role="dialog" aria-label="Presenter mode">
        {scene(true)}
        <button className="btn ghost absolute right-3 top-3" onClick={exit} aria-label="Exit presenter mode">Exit (X)</button>
      </div>
    );
  }

  return (
    <section className="grid gap-3" aria-label="Investor panel">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold m-0">Investor panel: {a.lenses.length} investors on {c.name}</h2>
          <p className="mute text-sm m-0 mt-1 max-w-3xl">A short prologue plays first: each investor works through their own checks and gives a reading, then those who disagree argue it out in front of a judge. Watch it through and you can question any of them. Every check is written out in the Report tab.</p>
        </div>
        <button className="btn ghost" onClick={present} title="Full-screen, for showing to a room">Present</button>
      </div>
      {scene(false)}
      <InvestorCards lenses={a.lenses} />
    </section>
  );
}

/** The investors without the 3D scene: roster, the sharpest disagreement, and the same one-on-one chat. */
function Plain({ r, why, onPlay }: { r: Report; why: string; onPlay?: () => void }) {
  const lenses = r.analysis!.lenses;
  const faceoffs = useMemo(() => pickFaceOffs(lenses), [lenses]);
  const [sel, setSel] = useState<number | null>(null);
  const [chats, setChats] = useState<Record<string, ChatMsg[]>>({});
  const key = sel != null ? lenses[sel].key : "";

  return (
    <section className="grid gap-4" aria-label="Investor panel">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-semibold m-0">Investor panel: {r.company.name}</h2>
          <p className="mute text-sm m-0 mt-1 max-w-3xl">Choose an investor to ask why they reached their reading. {why}</p>
        </div>
        {onPlay && <button className="btn ghost" onClick={onPlay}>Show the 3D view</button>}
      </div>

      <InvestorRoster lenses={lenses} sel={sel} onChoose={(i) => setSel((s) => (s === i ? null : i))} />

      <div className="card p-4 grid gap-3" role="region" aria-label={faceoffs.length ? "Where the investors disagree" : "No face-off"}>
        <div className="mute text-[11px] font-semibold uppercase tracking-wide">{faceoffs.length ? (faceoffs.length > 1 ? `${faceoffs.length} face-offs` : "Where they disagreed") : "No face-off"}</div>
        {faceoffs.length === 0 && <p className="m-0 text-sm">All six read it much the same way, so there was nothing to argue over.</p>}
        {faceoffs.map((f, k) => (
          <div key={k} className="grid gap-1.5">
            <b className="text-sm">{surname(lenses[f.pair[0]])} vs {surname(lenses[f.pair[1]])}</b>
            {f.turns.map((turn, j) => (
              <div key={j} className="text-sm" style={{ lineHeight: 1.4 }}>
                {turn.role === "ruling" && <div><b style={{ color: "#e6c350" }}>⚖ Judge {lenses[turn.by].name}: {turn.headline}</b> <span className="mute text-xs">Their own check:</span></div>}
                <b style={{ color: turn.quote.color }}>{turn.quote.mark} {turn.role === "ruling" ? "" : `${lenses[turn.by].name} · `}{turn.quote.head}</b>
                <div className="num mute text-xs">{turn.quote.shown}</div>
                <div className="mute text-xs">Idea: {turn.quote.idea}</div>
              </div>
            ))}
          </div>
        ))}
      </div>

      <InvestorCards lenses={lenses} />

      {sel != null && (
        <InvestorPanel key={key} inline cik={r.company.cik} lens={lenses[sel]} onClose={() => setSel(null)}
          messages={chats[key] ?? []} setMessages={(f) => setChats((c) => ({ ...c, [key]: f(c[key] ?? []) }))} />
      )}
    </section>
  );
}
