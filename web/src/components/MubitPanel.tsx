import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { api, pct, type MubitState } from "../api/client";
import { ErrorBox, Skeleton, Spark2 } from "./bits";

/** Mubit panel: per-agent track record, model version, and the latest "what it learned" story. */
export default function MubitPanel({ agents, asOf }: { agents: MubitState[]; asOf: string }) {
  const [sel, setSel] = useState(agents[0]?.agent);
  const m = agents.find((a) => a.agent === sel) ?? agents[0];
  const tr = useQuery({ queryKey: ["track", m?.agent, asOf], queryFn: () => api.trackRecord(m!.agent, asOf), enabled: !!m });
  if (!m) return <div className="card p-5 mute">No Mubit state for this quarter yet.</div>;
  const c = tr.data?.last_correction ?? m.last_correction;

  return (
    <div className="card p-4 md:p-6">
      <div role="tablist" aria-label="Analyst" className="flex flex-wrap gap-2 mb-5">
        {agents.map((a) => (
          <button key={a.agent} role="tab" aria-selected={a.agent === m.agent} onClick={() => setSel(a.agent)}
            className="chip cursor-pointer bg-transparent" style={a.agent === m.agent ? { color: "var(--text)", borderColor: "var(--blue)", background: "var(--panel2)" } : undefined}>
            {a.investor}
          </button>
        ))}
      </div>
      <AnimatePresence mode="wait">
        <motion.div key={m.agent} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} className="grid gap-5 md:grid-cols-2">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold">{m.investor}</span>
              <span className="chip num" title="Model version in force at this date">{m.model_version ?? "version n/a"}</span>
            </div>
            <div className="flex gap-6 mt-4">
              <Stat label="recent accuracy" value={m.accuracy == null ? "n/a" : pct(m.accuracy)} />
              <Stat label="graded calls" value={String(m.calls_graded)} />
              <Stat label="corrections" value={String(m.corrections_applied)} />
              {tr.data?.brier != null && <Stat label="Brier" value={tr.data.brier.toFixed(2)} />}
            </div>
            <div className="mt-4">
              {tr.isLoading ? <Skeleton h={56} /> : tr.isError ? <ErrorBox msg="Track record unavailable." onRetry={() => tr.refetch()} /> :
                <><Spark2 learned={tr.data!.learned} frozen={tr.data!.frozen} />
                  <div className="mute text-xs mt-1 flex gap-4"><span style={{ color: "var(--green)" }}>— learns with Mubit</span><span>- - frozen twin</span></div></>}
            </div>
          </div>
          <div>
            {c ? (
              <div className="rounded-xl p-4 h-full" style={{ background: "var(--panel2)" }}>
                <div className="mute text-xs uppercase tracking-wider mb-2">What it learned · {c.as_of}</div>
                <Row k="The call">predicted <b>{c.predicted ?? "n/a"}</b></Row>
                <Row k="What happened"><b>{c.actual ?? "n/a"}</b>{c.error_type ? <span className="mute"> · {c.error_type.replaceAll("_", " ")}</span> : null}</Row>
                <Row k="Lesson">{c.lesson ?? c.summary}</Row>
                <Row k="Update ref"><span className="num">{c.mubit_ref ?? "n/a"}</span></Row>
                <Row k="Model version"><span className="num">{c.version_before ?? "n/a"} → {c.version_after ?? "pending"}</span></Row>
                {c.reasked_answer && <Row k="Re-asked after update"><b>{c.reasked_answer}</b></Row>}
                {m.fallback_updater && <div className="mute text-xs mt-3">Applied by the offline fallback updater, not live Mubit.</div>}
              </div>
            ) : <div className="rounded-xl p-4 mute text-sm h-full" style={{ background: "var(--panel2)" }}>No wrong calls yet, so nothing to learn from at this date.</div>}
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

const Stat = ({ label, value }: { label: string; value: string }) => (
  <div><div className="num text-2xl font-semibold">{value}</div><div className="mute text-xs">{label}</div></div>
);
const Row = ({ k, children }: { k: string; children: React.ReactNode }) => (
  <div className="grid grid-cols-[110px_1fr] gap-2 text-sm py-1"><span className="mute">{k}</span><span>{children}</span></div>
);
