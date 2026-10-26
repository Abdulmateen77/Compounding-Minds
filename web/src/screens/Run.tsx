import { Component, lazy, Suspense, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { STANCE_COLOR, api, pct, type AgentView } from "../api/client";
import { Revision, Skeleton } from "../components/bits";
import { assessHref, go, useReducedMotion } from "../route";
import type { StreamVerdict } from "../scene/LiveScene";

// The 3D scene (three + react-three-fiber) is its own chunk so the Select screen stays light.
const LiveScene = lazy(() => import("../scene/LiveScene"));

const STAGES = [
  { id: "ingest", label: "Ingest filings" },
  { id: "metrics", label: "Compute metrics" },
  { id: "committee", label: "Committee calls" },
  { id: "cross_exam", label: "Cross-examination" },
  { id: "synthesis", label: "Weigh by track record" },
] as const;

type Status = "idle" | "start" | "done";

function hasWebGL() {
  try {
    const c = document.createElement("canvas");
    return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
  } catch { return false; }
}

/** `?scene=off` forces the 2D pipeline, `?scene=on` forces the 3D scene (ignores reduced motion). */
function initialMode(reduced: boolean): "3d" | "2d" {
  const q = new URLSearchParams(window.location.search).get("scene");
  if (q === "off") return "2d";
  if (q === "on") return hasWebGL() ? "3d" : "2d";
  return reduced || !hasWebGL() ? "2d" : "3d";
}

class SceneBoundary extends Component<{ onError: (why: string) => void; children: ReactNode }, { bad: boolean }> {
  state = { bad: false };
  static getDerivedStateFromError() { return { bad: true }; }
  componentDidCatch(e: unknown) { console.warn("scene failed, falling back to 2D", e); this.props.onError(String((e as Error)?.message ?? e)); }
  render() { return this.state.bad ? null : this.props.children; }
}

export default function Run({ id }: { id: string }) {
  const onDone = useCallback(() => go(assessHref(id)), [id]);
  const onBack = () => go("#/");
  const reduced = useReducedMotion();
  const [mode, setMode] = useState<"3d" | "2d">(() => initialMode(reduced));
  const modeAtConnect = useRef(mode);
  const [flipped, setFlipped] = useState(false);
  const [status, setStatus] = useState<Record<string, Status>>({});
  const [detail, setDetail] = useState<Record<string, string>>({});
  const [startDetail, setStartDetail] = useState<Record<string, string>>({});  // first detail seen per stage, for the scene caption
  const [calls, setCalls] = useState<AgentView[]>([]);
  const [verdict, setVerdict] = useState<StreamVerdict>(null);
  const [done, setDone] = useState(false);
  const [failed, setFailed] = useState(false);
  const finished = useRef(false);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  const assessment = useQuery({ queryKey: ["assessment", id], queryFn: () => api.assessment(id), enabled: mode === "3d", retry: 1 });
  const fallBack = useCallback((why: string) => { console.warn("3D scene off:", why); setFlipped(true); setMode("2d"); }, []);
  useEffect(() => { if (assessment.isError) fallBack("assessment fetch failed"); }, [assessment.isError, fallBack]);

  useEffect(() => {
    // The 3D scene paces itself, so ask the replay for all events at once; the 2D list keeps the server pacing.
    const es = new EventSource(`/api/assessments/${id}/events${modeAtConnect.current === "3d" ? "?pause=0" : ""}`);
    es.addEventListener("stage", (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setStatus((s) => ({ ...s, [d.stage]: d.status }));
      setDetail((s) => ({ ...s, [d.stage]: d.detail }));
      setStartDetail((s) => (s[d.stage] ? s : { ...s, [d.stage]: d.detail }));
    });
    es.addEventListener("agent_call", (e) => setCalls((c) => [...c, JSON.parse((e as MessageEvent).data)]));
    es.addEventListener("verdict", (e) => setVerdict(JSON.parse((e as MessageEvent).data)));
    es.addEventListener("done", () => { finished.current = true; setDone(true); es.close(); });
    es.onerror = () => { if (!finished.current) { es.close(); setFailed(true); } };
    return () => es.close();
  }, [id]);

  // 2D mode keeps the original behaviour: short pause after "done", then the verdict page.
  useEffect(() => {
    if (!done || mode !== "2d" || flipped) return;
    const t = setTimeout(() => doneRef.current(), 900);
    return () => clearTimeout(t);
  }, [done, mode, flipped]);

    const scene = mode === "3d";

  return (
    <div>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h1 className="text-2xl md:text-3xl font-bold m-0">The committee is working</h1>
        {!scene && (
          <span className="flex gap-2">
            <button className="btn ghost" onClick={() => { setFlipped(false); setMode("3d"); }} disabled={!hasWebGL()}>3D scene</button>
            <button className="btn ghost" onClick={onDone}>Skip to verdict</button>
          </span>
        )}
      </div>
      <p className="mute mt-2">Replaying a stored run. Nothing here calls a live service.</p>

      {scene ? (
        assessment.data ? (
          <div className="mt-6 relative left-1/2 -translate-x-1/2" style={{ width: "min(1240px, calc(100vw - 2rem))" }}>
            <SceneBoundary onError={fallBack}>
              <Suspense fallback={<Skeleton h={420} />}>
                <LiveScene assessment={assessment.data} calls={calls} verdict={verdict} done={done} failed={failed}
                  stageDetail={startDetail} onFinish={onDone} onFlat={() => fallBack("user chose 2D")} onFail={fallBack} />
              </Suspense>
            </SceneBoundary>
          </div>
        ) : <div className="mt-6"><Skeleton h={420} /></div>
      ) : (
        <div className="grid gap-6 mt-6 md:grid-cols-[280px_1fr]">
          <ol className="card p-5 m-0 list-none grid gap-5 self-start">
            {STAGES.filter((s) => s.id !== "cross_exam" || status.cross_exam).map((s) => {
              const st = status[s.id] ?? "idle";
              return (
                <li key={s.id} className="flex gap-3 items-start">
                  <motion.span animate={{ scale: st === "start" ? [1, 1.25, 1] : 1 }} transition={{ repeat: st === "start" ? Infinity : 0, duration: 1.1 }}
                    className="mt-1 w-3 h-3 rounded-full shrink-0"
                    style={{ background: st === "done" ? "var(--success)" : st === "start" ? "var(--primary)" : "var(--divider)" }} />
                  <div><div className="font-medium" style={{ opacity: st === "idle" ? 0.45 : 1 }}>{s.label}</div>
                    {detail[s.id] && <div className="mute text-sm">{detail[s.id]}</div>}</div>
                </li>
              );
            })}
          </ol>

          <div className="grid gap-3 content-start">
            {calls.length === 0 && <div className="card p-5 mute">Waiting for the first investor…</div>}
            {calls.map((c) => (
              <motion.div key={c.agent} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} className="card p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-semibold">{c.investor} <span className="mute font-normal text-sm">· {c.agent}</span></div>
                  <span className="chip" style={{ color: STANCE_COLOR[c.stance], borderColor: STANCE_COLOR[c.stance] }}>{c.stance}</span>
                </div>
                <div className="mute text-sm mt-1">{c.question}</div>
                <div className="mt-2 text-sm"><b>{c.answer}</b> <span className="num mute">at {pct(c.probability)}</span> <Revision from={c.revised_from} to={c.probability} /></div>
              </motion.div>
            ))}
          </div>
        </div>
      )}
      {failed && !scene && <p style={{ color: "var(--error)" }} className="mt-4">The stream dropped. <button className="btn ghost" onClick={onDone}>Show result</button> <button className="btn ghost" onClick={onBack}>Back</button></p>}
      {failed && scene && <p style={{ color: "var(--error)" }} className="mt-4">The stream dropped; showing what arrived. <button className="btn ghost" onClick={onBack}>Back</button></p>}
    </div>
  );
}
