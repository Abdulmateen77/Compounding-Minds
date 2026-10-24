import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { LABELS, STANCE_COLOR, api, pct, type AgentView } from "../api/client";
import { ErrorBox, Revision, Skeleton, Spark, StubChip, VoteBar, Ring, fmt } from "../components/bits";
import MubitPanel from "../components/MubitPanel";

export default function Verdict({ id, onBack }: { id: string; onBack: () => void }) {
  const q = useQuery({ queryKey: ["assessment", id], queryFn: () => api.assessment(id) });
  if (q.isLoading) return <div className="grid gap-4"><Skeleton h={200} /><div className="grid gap-3 md:grid-cols-2"><Skeleton /><Skeleton /></div></div>;
  if (q.isError || !q.data) return <div className="grid gap-3"><ErrorBox msg="Could not load this assessment." onRetry={() => q.refetch()} /><button className="btn ghost justify-self-start" onClick={onBack}>← Another company</button></div>;
  const a = q.data, L = LABELS[a.label];

  return (
    <div className="grid gap-6">
      <button className="btn ghost self-start justify-self-start" onClick={onBack}>← Another company</button>

      <motion.section initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="card p-6 md:p-8 grid gap-6 md:grid-cols-[auto_1fr] items-center"
        style={{ background: `linear-gradient(135deg, color-mix(in srgb, ${L.color} 14%, var(--panel)), var(--panel))`, borderColor: `color-mix(in srgb, ${L.color} 45%, var(--line))` }}>
        <Ring value={a.confidence} color={L.color} />
        <div>
          <div className="mute text-sm flex items-center gap-2 flex-wrap">{a.company.name} · as of <span className="num">{a.as_of}</span>{a.stub && <StubChip />}</div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight my-1" style={{ color: L.color }}>{L.text}</h1>
          <p className="mute m-0 mb-4 text-sm">An evidence assessment from the committee, not investment advice or a recommendation to trade.</p>
          <div className="max-w-md"><VoteBar for_={a.votes.for} neutral={a.votes.neutral} against={a.votes.against} /></div>
        </div>
      </motion.section>

      {a.dissent.length > 0 && (
        <section className="card p-5">
          <h2 className="text-sm uppercase tracking-wider mute m-0 mb-2">Where the committee disagrees</h2>
          <ul className="m-0 pl-5 grid gap-1 text-sm">{a.dissent.map((d) => <li key={d}>{d}</li>)}</ul>
        </section>
      )}

      <section>
        <h2 className="text-sm uppercase tracking-wider mute mb-3">The committee</h2>
        <div className="grid gap-3 md:grid-cols-2">{a.committee.map((v) => <AgentCard key={v.agent} v={v} />)}</div>
      </section>

      <section>
        <h2 className="text-sm uppercase tracking-wider mute mb-3">Metrics behind the calls <span className="normal-case">(computed in Python)</span></h2>
        {a.metrics.length === 0 && <p className="mute text-sm">No metrics stored for this quarter.</p>}
        <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
          {a.metrics.map((m) => (
            <div key={m.name} className="card p-4">
              <div className="mute text-xs">{m.name.replaceAll("_", " ")}</div>
              <div className="num text-xl font-semibold my-1">{fmt(m.value, m.unit)}</div>
              <Spark data={m.trend} />
              <div className="mute text-[10px] mt-1 truncate" title={m.accessions?.[0]}>{m.accessions?.[0] ? `Filing ${m.accessions?.[0]}` : "Python-computed"}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <section className="card p-5">
          <h2 className="text-sm uppercase tracking-wider mute m-0 mb-3">Risks</h2>
          {a.risks.length ? <ul className="m-0 pl-5 grid gap-1 text-sm">{a.risks.map((r) => <li key={r}>{r}</li>)}</ul> : <p className="mute m-0 text-sm">No distress signals raised.</p>}
        </section>
        <section className="card p-5">
          <h2 className="text-sm uppercase tracking-wider mute m-0 mb-3">Scenario view</h2>
          {a.scenarios.length === 0 && <p className="mute m-0 text-sm">No scenario call at this date.</p>}
          {a.scenarios.map((s) => (
            <div key={s.bucket}>
              <div className="flex gap-2 mb-3">
                {["bear", "base", "bull"].map((b) => (
                  <div key={b} className="flex-1 text-center py-2 rounded-lg text-sm capitalize"
                    style={{ background: b === s.bucket ? "var(--blue)" : "var(--panel2)", color: b === s.bucket ? "#fff" : "var(--mute)" }}>{b}</div>
                ))}
              </div>
              <div className="text-sm mute">Revenue bucket at <span className="num">{pct(s.probability)}</span> confidence</div>
              <ul className="m-0 mt-2 pl-5 text-sm">{s.reasoning.map((r) => <li key={r}>{r}</li>)}</ul>
            </div>
          ))}
        </section>
      </div>

      <section>
        <h2 className="text-sm uppercase tracking-wider mute mb-1">Mubit · what each analyst has learned</h2>
        <p className="mute text-sm mt-0 mb-3">Wrong calls become corrections, and corrections become model updates.</p>
        <MubitPanel agents={a.mubit} asOf={a.as_of} />
      </section>
    </div>
  );
}

function AgentCard({ v }: { v: AgentView }) {
  const color = STANCE_COLOR[v.stance];
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="card p-5">
      <div className="flex items-center justify-between gap-2">
        <div className="font-semibold">{v.investor} <span className="mute font-normal text-sm">· {v.agent}</span></div>
        <span className="chip" style={{ color, borderColor: color }}>{v.stance}</span>
      </div>
      <div className="mute text-sm mt-1">{v.question}</div>
      <div className="mt-3 flex items-center flex-wrap gap-x-2 gap-y-1">
        <span className="text-xl font-bold capitalize">{v.answer}</span>
        <span className="num mute text-sm">{pct(v.confidence)} confident · weight {v.weight.toFixed(2)}</span>
        <Revision from={v.revised_from} to={v.probability} />
      </div>
      <ul className="m-0 mt-2 pl-5 text-sm grid gap-1">{v.reasoning.map((r) => <li key={r}>{r}</li>)}</ul>
      <div className="flex flex-wrap gap-2 mt-3">
        {v.evidence.map((e) => (
          <span key={e.metric} className="chip num" title={e.accession ? `Filing accession ${e.accession}` : "Computed in Python from stored filings"}>
            {e.metric.replaceAll("_", " ")} {fmt(e.value)}{e.accession ? <span style={{ color: "var(--blue)" }}> · {e.accession}</span> : null}
          </span>
        ))}
        {v.principles.map((p) => <span key={p} className="chip" style={{ color: "var(--purple)" }}>{p}</span>)}
      </div>
    </motion.div>
  );
}
