import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { STANCE_COLOR, pct, type AgentView } from "../api/client";
import { Revision } from "../components/bits";

const STAGES = [
  { id: "ingest", label: "Ingest filings" },
  { id: "metrics", label: "Compute metrics" },
  { id: "committee", label: "Committee calls" },
  { id: "cross_exam", label: "Cross-examination" },
  { id: "synthesis", label: "Weigh by track record" },
] as const;

type Status = "idle" | "start" | "done";

export default function Run({ id, onDone, onBack }: { id: string; onDone: () => void; onBack: () => void }) {
  const [status, setStatus] = useState<Record<string, Status>>({});
  const [detail, setDetail] = useState<Record<string, string>>({});
  const [calls, setCalls] = useState<AgentView[]>([]);
  const [failed, setFailed] = useState(false);
  const finished = useRef(false);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  useEffect(() => {
    const es = new EventSource(`/api/assessments/${id}/events`);
    es.addEventListener("stage", (e) => {
      const d = JSON.parse((e as MessageEvent).data);
      setStatus((s) => ({ ...s, [d.stage]: d.status }));
      setDetail((s) => ({ ...s, [d.stage]: d.detail }));
    });
    es.addEventListener("agent_call", (e) => setCalls((c) => [...c, JSON.parse((e as MessageEvent).data)]));
    es.addEventListener("done", () => { finished.current = true; es.close(); setTimeout(() => doneRef.current(), 900); });
    es.onerror = () => { if (!finished.current) { es.close(); setFailed(true); } };
    return () => es.close();
  }, [id]);

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight m-0">The committee is working</h1>
        <button className="btn ghost" onClick={onDone}>Skip to verdict</button>
      </div>
      <p className="mute mt-2">Replaying a stored run. Nothing here calls a live service.</p>

      <div className="grid gap-6 mt-6 md:grid-cols-[280px_1fr]">
        <ol className="card p-5 m-0 list-none grid gap-5 self-start">
          {STAGES.filter((s) => s.id !== "cross_exam" || status.cross_exam).map((s) => {
            const st = status[s.id] ?? "idle";
            return (
              <li key={s.id} className="flex gap-3 items-start">
                <motion.span animate={{ scale: st === "start" ? [1, 1.25, 1] : 1 }} transition={{ repeat: st === "start" ? Infinity : 0, duration: 1.1 }}
                  className="mt-1 w-3 h-3 rounded-full shrink-0"
                  style={{ background: st === "done" ? "var(--green)" : st === "start" ? "var(--blue)" : "var(--line)" }} />
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
      {failed && <p style={{ color: "var(--red)" }} className="mt-4">The stream dropped. <button className="btn ghost" onClick={onDone}>Show result</button> <button className="btn ghost" onClick={onBack}>Back</button></p>}
    </div>
  );
}
