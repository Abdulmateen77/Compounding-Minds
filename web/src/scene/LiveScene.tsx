import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { LABELS, STANCE_COLOR, pct, type AgentView, type Assessment } from "../api/client";
import { StubChip, fmt } from "../components/bits";
import { Director, useDirectorTick } from "./director";
import SceneContents, { type Els, type Orbit, type SceneAgent, type SceneCard, type SceneVerdict } from "./SceneContents";
import { lookFor } from "./theme";
import { agentState, phaseAt, type Phase } from "./timeline";

export type StreamVerdict = { label: keyof typeof LABELS; score: number; confidence: number } | null;

type Props = {
  assessment: Assessment;
  calls: AgentView[];
  verdict: StreamVerdict;
  done: boolean;
  failed: boolean;
  stageDetail: Record<string, string>;
  onFinish: () => void;   // hand off to the Verdict page
  onFlat: () => void;     // switch to the 2D pipeline view
  onFail: (why: string) => void;
};

const STAGES = [
  { id: "ingest", label: "Ingest filings" },
  { id: "metrics", label: "Compute metrics" },
  { id: "committee", label: "Committee calls" },
  { id: "cross_exam", label: "Cross-examination" },
  { id: "synthesis", label: "Weigh by track record" },
] as const;
const PHASE_ORDER: Phase[] = ["ingest", "metrics", "committee", "cross_exam", "synthesis", "done"];
const ORBIT_AZ = 0.5, ORBIT_POL = 0.2;
const DEFAULT_DETAIL: Record<string, string> = { cross_exam: "Confidence revised after peer review" };
const human = (s: string) => s.replace(/_/g, " ");

export default function LiveScene(props: Props) {
  const { assessment: a, calls, verdict, done, failed, stageDetail, onFinish, onFlat, onFail } = props;
  const n = a.committee.length;
  const hasCross = a.committee.some((c) => c.revised_from != null);

  const dir = useMemo(() => new Director(n, hasCross), [a.assessment_id, n, hasCross]);
  useEffect(() => { dir.start(); return () => dir.stop(); }, [dir]);
  dir.inputs = { calls: calls.length, verdict: !!verdict, done, failed };
  useDirectorTick(dir);

  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const callsRef = useRef(calls); callsRef.current = calls;
  const finishedStream = done || failed;
  const doneRef = useRef(finishedStream); doneRef.current = finishedStream;
  const getView = useCallback((i: number): AgentView | undefined => {
    const key = a.committee[i]?.agent;
    return callsRef.current.find((c) => c.agent === key) ?? (doneRef.current ? a.committee[i] : undefined);
  }, [a]);

  const agents = useMemo<SceneAgent[]>(() => a.committee.map((c) => ({
    key: c.agent, investor: c.investor, role: c.agent, look: lookFor(c.investor, c.agent), weight: c.weight,
    evidence: new Set(c.evidence.map((e) => e.metric)),
  })), [a]);

  // Metric cards: only real metrics from the assessment, those cited as evidence first.
  const cards = useMemo<SceneCard[]>(() => {
    const cited = a.committee.flatMap((c) => c.evidence.map((e) => e.metric));
    const order = [...new Set(cited), ...a.metrics.map((m) => m.name)];
    const byName = new Map(a.metrics.map((m) => [m.name, m]));
    return order.filter((nm) => byName.has(nm)).slice(0, 6).map((nm) => ({ name: nm, value: fmt(byName.get(nm)!.value, byName.get(nm)!.unit) }));
  }, [a]);

  const sceneVerdict: SceneVerdict = useMemo(() => {
    const v = verdict ?? (finishedStream ? { label: a.label, score: a.score, confidence: a.confidence } : null);
    return v ? { text: LABELS[v.label].text, label: v.label, confidence: v.confidence } : null;
  }, [verdict, finishedStream, a]);

  const mubitFor = useCallback((agent: string) => a.mubit.find((m) => m.agent === agent), [a]);

  // UI state
  const [hover, setHover] = useState<number | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const orbit = useRef<Orbit>({ az: 0, pol: 0 });
  const els = useRef<Els>({ chips: [], wchips: [], bubble: null, focus: -1 });
  const drag = useRef<{ x: number; y: number; az: number; pol: number } | null>(null);

  const t = dir.clock;
  const phase = phaseAt(dir.tl, t);
  const speaking = Array.from({ length: n }, (_, i) => i).find((i) => agentState(dir.tl, i, t) === "speaking") ?? -1;
  const focus = sel != null ? -1 : (hover ?? (speaking >= 0 ? speaking : -1));
  els.current.focus = focus;

  // Hand off to the Verdict page once the scene has played out and the stream is done.
  const idle = useRef<number | undefined>(undefined);
  const canFinish = dir.finished && done && dir.playing && sel == null;
  useEffect(() => {
    if (!canFinish) return;
    idle.current = window.setTimeout(onFinish, 1800);
    return () => window.clearTimeout(idle.current);
  }, [canFinish, onFinish]);

  // If the stream dies and we have nothing to show, give up gracefully.
  useEffect(() => { if (failed && calls.length === 0 && !done) onFail("stream"); }, [failed, calls.length, done, onFail]);

  const orbitBy = (daz: number, dpol: number) => {
    orbit.current.az = Math.max(-ORBIT_AZ, Math.min(ORBIT_AZ, orbit.current.az + daz));
    orbit.current.pol = Math.max(-ORBIT_POL * 0.6, Math.min(ORBIT_POL, orbit.current.pol + dpol));
  };
  const onKey = (e: React.KeyboardEvent) => {
    const k = e.key;
    if (k === "ArrowLeft") orbitBy(-0.08, 0); else if (k === "ArrowRight") orbitBy(0.08, 0);
    else if (k === "ArrowUp") orbitBy(0, 0.05); else if (k === "ArrowDown") orbitBy(0, -0.05);
    else if (k === " " && e.target === e.currentTarget) dir.setPlaying(!dir.playing);
    else if (k === "Escape") setSel(null);
    else if (k === "0") orbit.current = { az: 0, pol: 0 };
    else return;
    e.preventDefault();
  };

  const view = focus >= 0 ? getView(focus) : undefined;
  const focusMubit = focus >= 0 ? mubitFor(a.committee[focus].agent) : undefined;
  const sinceSpeak = focus >= 0 ? t - dir.tl.speak[focus] : 0;
  const showLesson = focus >= 0 && (focus !== speaking || sinceSpeak > 1.5);

  const stageStatus = (id: string) => {
    if (id === "cross_exam" && !hasCross) return null;
    const pi = PHASE_ORDER.indexOf(id as Phase), ci = PHASE_ORDER.indexOf(phase);
    return pi < ci ? "done" : pi === ci ? "start" : "idle";
  };
  const activeStage = STAGES.find((s) => s.id === phase);
  const srLine = view && speaking >= 0 ? `${a.committee[speaking].investor} says ${view.answer}, confidence ${pct(view.confidence)}. ${view.reasoning[0] ?? ""}` : "";

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_270px]">
      <div>
        <div
          className="relative rounded-2xl overflow-hidden border select-none outline-none focus-visible:ring-2"
          style={{ borderColor: "var(--line)", background: "#121831", aspectRatio: "16 / 9", minHeight: 380, touchAction: "pan-y" }}
          tabIndex={0} role="group" aria-label="Committee scene. Drag or use arrow keys to tilt the camera, space to pause."
          onKeyDown={onKey}
          onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, az: orbit.current.az, pol: orbit.current.pol }; }}
          onPointerMove={(e) => {
            const d = drag.current; if (!d || e.buttons === 0) return;
            const w = e.currentTarget.clientWidth;
            orbit.current.az = Math.max(-ORBIT_AZ, Math.min(ORBIT_AZ, d.az - ((e.clientX - d.x) / w) * 1.6));
            orbit.current.pol = Math.max(-ORBIT_POL * 0.6, Math.min(ORBIT_POL, d.pol + ((e.clientY - d.y) / w) * 1.2));
          }}
          onPointerUp={() => { drag.current = null; }}
          onPointerLeave={() => { drag.current = null; }}
        >
          <Canvas
            shadows dpr={[1, 2]} camera={{ fov: 35, position: [0, 3.6, 11], near: 0.1, far: 60 }}
            gl={{ antialias: true, powerPreference: "high-performance" }}
            onCreated={({ gl }) => gl.domElement.addEventListener("webglcontextlost", () => { if (alive.current) onFail("webgl context lost"); })}
          >
            <SceneContents dir={dir} agents={agents} cards={cards} verdict={sceneVerdict} getView={getView}
              orbit={orbit} els={els} company={{ name: a.company.name, sector: a.company.sector ?? "", asOf: a.as_of }}
              onHover={setHover} onSelect={(i) => setSel((s) => (s === i ? null : i))} />
          </Canvas>

          {/* title */}
          <div className="absolute left-3 top-3 flex items-center gap-2 pointer-events-none">
            <span className="chip" style={{ background: "color-mix(in srgb, var(--panel) 85%, transparent)", color: "var(--text)" }}>
              {a.company.name}{a.company.sector ? ` · ${a.company.sector}` : ""} · as of <span className="num">{a.as_of}</span>
            </span>
            {a.stub && <StubChip />}
          </div>

          {/* per-desk chips */}
          {a.committee.map((c, i) => {
            const st = agentState(dir.tl, i, t), v = getView(i);
            const showRev = v?.revised_from != null && Math.abs(v.revised_from - v.probability) >= 0.005 && phase !== "ingest" && phase !== "metrics" && phase !== "committee";
            const showW = phase === "synthesis" || phase === "done";
            return (
              <div key={c.agent} ref={(el) => { els.current.chips[i] = el; }} className="absolute left-0 top-0 pointer-events-none flex flex-col items-center gap-1" style={{ willChange: "transform" }}>
                {showRev && v && <span className="chip num" style={{ background: "var(--panel)", color: "var(--amber)", borderColor: "var(--amber)" }}>{pct(v.revised_from!)} {v.probability > v.revised_from! ? "↗" : "↘"} {pct(v.probability)}</span>}
                {st === "thinking" && <span className="chip" style={{ background: "var(--panel)" }}>thinking…</span>}
                {(st === "speaking" || st === "done") && v && (
                  <span className="chip num font-semibold" style={{ background: "var(--panel)", color: STANCE_COLOR[v.stance], borderColor: STANCE_COLOR[v.stance] }}>
                    {v.answer.toUpperCase()} · {pct(v.confidence)}
                  </span>
                )}
              </div>
            );
          })}

          {/* committee weights, shown on the floor in front of each desk during synthesis */}
          {a.committee.map((c, i) => (
            <div key={c.agent} ref={(el) => { els.current.wchips[i] = el; }} className="absolute left-0 top-0 pointer-events-none" style={{ willChange: "transform", opacity: phase === "synthesis" || phase === "done" ? 1 : 0, transition: "opacity .4s" }}>
              <span className="chip num" style={{ background: "var(--panel)", color: "#c9b8ff", borderColor: "#7b5cff" }}>weight {c.weight.toFixed(2)}</span>
            </div>
          ))}

          {/* speech bubble / hover card */}
          <div ref={(el) => { els.current.bubble = el; }} className="absolute left-0 top-0 pointer-events-none"
            style={{ width: 300, opacity: view && focus >= 0 ? 1 : 0, transition: "opacity .2s", willChange: "transform" }}>
            {view && focus >= 0 && (
              <div className="rounded-xl p-3 text-sm shadow-xl" style={{ background: "var(--panel)", border: `2px solid ${STANCE_COLOR[view.stance]}`, color: "var(--text)" }}>
                <div className="flex items-center justify-between gap-2">
                  <b>{view.investor}</b>
                  <span className="chip num" title="Model version making this call">{view.model}</span>
                </div>
                <div className="mute text-xs mt-1">{view.question}</div>
                <div className="mt-1.5"><b style={{ color: STANCE_COLOR[view.stance], fontSize: "1.05rem" }}>{view.answer.toUpperCase()}</b> <span className="num mute">confidence {pct(view.confidence)}</span></div>
                {view.reasoning[0] && <div className="mt-1 text-xs" style={{ lineHeight: 1.35 }}>{view.reasoning[0]}</div>}
                {showLesson && (
                  <div className="mt-2 rounded-lg p-2 text-xs" style={{ background: "color-mix(in srgb, var(--purple) 16%, transparent)", border: "1px solid var(--purple)" }}>
                    <div className="font-semibold" style={{ color: "var(--purple)" }}>
                      LESSON APPLIED{focusMubit?.fallback_updater ? " · offline fallback updater, not live Mubit" : " · Mubit"}
                    </div>
                    {focusMubit?.last_correction ? (<>
                      <div className="mt-0.5" style={{ lineHeight: 1.35 }}>{focusMubit.last_correction.lesson ?? focusMubit.last_correction.summary}</div>
                      <div className="num mute mt-0.5">{focusMubit.last_correction.version_before ?? "n/a"} → {focusMubit.last_correction.version_after ?? "pending"}</div>
                    </>) : <div className="mute mt-0.5">No correction on record yet for this agent.</div>}
                  </div>
                )}
              </div>
            )}
            <div style={{ width: 0, height: 0, margin: "0 auto", borderLeft: "8px solid transparent", borderRight: "8px solid transparent", borderTop: `8px solid ${view ? STANCE_COLOR[view.stance] : "transparent"}`, transform: "translateX(var(--tail,0px))" }} />
          </div>

          {/* caption */}
          <div className="absolute left-3 bottom-3 right-3 flex items-end justify-between gap-3 pointer-events-none">
            <div className="rounded-lg px-3 py-2 text-sm" style={{ background: "color-mix(in srgb, var(--panel) 88%, transparent)", border: "1px solid var(--line)", maxWidth: "62%" }}>
              {dir.waiting ? <span className="mute">Waiting for the next event from the stream…</span>
                : phase === "done" ? <b>Assessment ready</b>
                : <><b>{activeStage?.label}</b><span className="mute"> · {stageDetail[phase] ?? DEFAULT_DETAIL[phase] ?? ""}</span></>}
            </div>
            {sceneVerdict && t >= dir.tl.stamp && (
              <div className="rounded-lg px-3 py-2 text-sm text-right pointer-events-auto" style={{ background: "var(--panel)", border: `2px solid ${LABELS[sceneVerdict.label].color}` }}>
                <div className="font-bold" style={{ color: LABELS[sceneVerdict.label].color }}>{sceneVerdict.text}</div>
                <div className="num mute text-xs">confidence {pct(sceneVerdict.confidence ?? 0)} · evidence assessment</div>
              </div>
            )}
          </div>

          {/* selected analyst card */}
          {sel != null && (
            <aside className="absolute right-3 top-3 bottom-16 w-72 max-w-[75%] overflow-auto rounded-xl p-3 text-sm" style={{ background: "var(--panel)", border: "1px solid var(--line)" }} aria-label={`${a.committee[sel].investor} reasoning`}>
              <div className="flex justify-between items-start gap-2">
                <div><b>{a.committee[sel].investor}</b> <span className="mute text-xs">· {a.committee[sel].agent}</span></div>
                <button className="btn ghost" style={{ padding: ".15rem .55rem" }} onClick={() => setSel(null)} aria-label="Close analyst card">×</button>
              </div>
              <AnalystDetail v={getView(sel)} mubit={mubitFor(a.committee[sel].agent)} />
            </aside>
          )}
          <div className="sr-only" aria-live="polite">{srLine}</div>
        </div>

        {/* controls */}
        <div className="flex flex-wrap items-center gap-2 mt-3" role="toolbar" aria-label="Scene controls">
          <button className="btn ghost" onClick={() => (dir.finished ? dir.replay() : dir.setPlaying(!dir.playing))} aria-pressed={!dir.playing}>
            {dir.finished ? "Replay" : dir.playing ? "Pause" : "Resume"}
          </button>
          {[1, 2].map((s) => (
            <button key={s} className="btn ghost" aria-pressed={dir.speed === s} onClick={() => dir.setSpeed(s)}
              style={dir.speed === s ? { color: "var(--text)", borderColor: "var(--blue)" } : undefined}>{s}x</button>
          ))}
          <button className="btn ghost" onClick={() => { orbit.current = { az: 0, pol: 0 }; }}>Reset view</button>
          <div className="flex-1 min-w-[80px] h-1.5 rounded-full overflow-hidden" style={{ background: "var(--line)" }} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((t / dir.tl.end) * 100)} aria-label="Scene progress">
            <div style={{ width: `${(t / dir.tl.end) * 100}%`, height: "100%", background: "var(--blue)" }} />
          </div>
          <button className="btn ghost" onClick={onFlat}>2D view</button>
          <button className="btn" onClick={onFinish}>Skip to verdict</button>
        </div>
        <p className="mute text-xs mt-2 mb-0">Drag to tilt the camera. Hover or click an analyst for their reasoning and evidence.</p>
      </div>

      {/* compact stage ticker + investor list */}
      <div className="grid gap-4 content-start">
        <ol className="card p-4 m-0 list-none grid gap-3" aria-label="Pipeline stages">
          {STAGES.map((s) => {
            const st = stageStatus(s.id); if (!st) return null;
            return (
              <li key={s.id} className="flex gap-3 items-start">
                <span className="mt-1.5 w-2.5 h-2.5 rounded-full shrink-0" style={{ background: st === "done" ? "var(--green)" : st === "start" ? "var(--blue)" : "var(--line)" }} />
                <div><div className="text-sm font-medium" style={{ opacity: st === "idle" ? 0.45 : 1 }}>{s.label}</div>
                  {st !== "idle" && (stageDetail[s.id] ?? DEFAULT_DETAIL[s.id]) && <div className="mute text-xs">{stageDetail[s.id] ?? DEFAULT_DETAIL[s.id]}</div>}</div>
              </li>
            );
          })}
        </ol>
        <div className="card p-3 grid gap-1.5" aria-label="Investors">
          {a.committee.map((c, i) => {
            const v = agentState(dir.tl, i, t) === "speaking" || agentState(dir.tl, i, t) === "done" ? getView(i) : undefined;
            return (
              <button key={c.agent} onClick={() => setSel((s) => (s === i ? null : i))} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}
                className="flex items-center justify-between gap-2 text-left text-sm rounded-lg px-2 py-1.5 cursor-pointer"
                style={{ background: sel === i ? "var(--panel2)" : "transparent", border: "1px solid var(--line)", color: "var(--text)" }} aria-pressed={sel === i}>
                <span>{c.investor} <span className="mute text-xs">· {c.agent}</span></span>
                {v ? <span className="chip" style={{ color: STANCE_COLOR[v.stance], borderColor: STANCE_COLOR[v.stance] }}>{v.answer} · {pct(v.confidence)}</span>
                  : <span className="mute text-xs">{agentState(dir.tl, i, t) === "thinking" ? "thinking…" : "waiting"}</span>}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function AnalystDetail({ v, mubit }: { v?: AgentView; mubit?: Assessment["mubit"][number] }) {
  if (!v) return <p className="mute mt-2">Still thinking. Their call has not landed yet.</p>;
  const lc = mubit?.last_correction;
  return (
    <div className="mt-2 grid gap-2">
      <div className="mute text-xs">{v.question}</div>
      <div><b style={{ color: STANCE_COLOR[v.stance], fontSize: "1.1rem" }}>{v.answer.toUpperCase()}</b> <span className="num mute">confidence {pct(v.confidence)}</span></div>
      <ul className="m-0 pl-4 text-xs grid gap-1">{v.reasoning.map((r, i) => <li key={i}>{r}</li>)}</ul>
      {v.evidence.length > 0 && (
        <div><div className="mute text-xs mb-1">Evidence</div>
          <div className="flex flex-wrap gap-1">{v.evidence.map((e, i) => <span key={i} className="chip num">{human(e.metric)}: {e.value}</span>)}</div></div>
      )}
      <div className="mute text-xs">Model <span className="num">{v.model}</span></div>
      {lc && <div className="text-xs rounded-lg p-2" style={{ border: "1px solid var(--purple)" }}>
        <b style={{ color: "var(--purple)" }}>Lesson applied{mubit?.fallback_updater ? " (offline fallback updater)" : ""}</b>
        <div className="mt-0.5">{lc.lesson ?? lc.summary}</div>
        <div className="num mute">{lc.version_before ?? "n/a"} → {lc.version_after ?? "pending"}</div></div>}
    </div>
  );
}
