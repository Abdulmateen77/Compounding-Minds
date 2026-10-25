import { useQueries, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { api, pct, type Correction, type HeldOutReport, type Score, type TrackRecord } from "../api/client";
import { ErrorBox, Skeleton, StubChip } from "../components/bits";
import { go, mubitHref } from "../route";
import { EvidencePanel } from "./ResearchAnalysis";
import { DUR } from "../motion";

const AGENTS = ["fundamentals", "risk", "scenarios"] as const; // the MVP committee; Valuation is a stretch agent
const ROLE: Record<string, string> = { fundamentals: "Fundamentals", valuation: "Valuation", moat: "Moat", risk: "Risk", scenarios: "Scenarios" };
const last = (x: number[]) => (x.length ? x[x.length - 1] : null);
const avg = (x: number[]) => (x.length ? x.reduce((a, b) => a + b, 0) / x.length : null);

export default function Mubit({ agent }: { agent?: string }) {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const qs = useQueries({ queries: AGENTS.map((a) => ({ queryKey: ["track", a], queryFn: () => api.trackRecord(a) })) });
  const loading = qs.some((q) => q.isLoading);
  const data = qs.map((q) => q.data).filter((d): d is TrackRecord => !!d);
  const failed = qs.every((q) => q.isError);
  const sel = data.find((d) => d.agent === agent) ?? data[0];

  const learnedNow = avg(data.map((d) => last(d.learned)).filter((x): x is number => x != null));
  const frozenNow = avg(data.map((d) => last(d.frozen)).filter((x): x is number => x != null));
  const brier = avg(data.map((d) => d.brier).filter((x): x is number => x != null));
  const corrections = data.reduce((n, d) => n + d.corrections_applied, 0);
  const graded = data.reduce((n, d) => n + d.calls_graded, 0);
  const lift = learnedNow != null && frozenNow != null ? Math.round((learnedNow - frozenNow) * 100) : null;
  const asOf = data[0]?.as_of;
  const [tab, setTab] = useState<"checks" | "learning">(agent ? "learning" : "checks");

  return (
    <div className="grid gap-6">
      <div>
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-3xl md:text-4xl font-bold m-0">Track record</h1>
          {health.data?.stub !== false && tab === "learning" && <StubChip />}
        </div>
        <p className="mute mt-2 mb-0 max-w-2xl">Two tests of whether this can be trusted: do the checks tell good businesses from weak ones, and do the AI analysts improve when they are wrong?</p>
      </div>

      <div role="tablist" aria-label="Track record" className="flex gap-1 p-1 rounded-xl justify-self-start max-w-full tabrow" style={{ background: "var(--card-alt)", border: "1px solid var(--divider)" }}>
        {([["checks", "Do the checks work?"], ["learning", "Do the analysts learn?"]] as const).map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)} className="px-4 py-2 rounded-lg text-sm font-medium cursor-pointer border-0 whitespace-nowrap"
            style={tab === id ? { background: "var(--card)", color: "var(--foreground)", boxShadow: "0 0 0 1px var(--divider)" } : { background: "transparent", color: "var(--muted)" }}>{label}</button>
        ))}
      </div>

      {tab === "checks" && <EvidencePanel />}
      {tab === "learning" && (<>
        <p className="mute m-0 max-w-2xl text-sm">Every wrong call becomes a lesson that goes into the analyst's next prompt, and Mubit records the calls. Each analyst here is compared with a frozen twin that never gets lessons.{asOf && <> Figures run to <span className="num">{asOf}</span>.</>}</p>

      {failed && <ErrorBox msg="Could not load track records. Is the API running?" onRetry={() => qs.forEach((q) => q.refetch())} />}
      {loading && <div className="grid gap-3 grid-cols-2 md:grid-cols-4"><Skeleton h={96} /><Skeleton h={96} /><Skeleton h={96} /><Skeleton h={96} /></div>}

      {data.length > 0 && (
        <>
          <section aria-label="Summary" className="grid gap-3 grid-cols-2 md:grid-cols-4">
            <Kpi label="Corrections applied" value={String(corrections)} note="across all analysts" />
            <Kpi label="Calls graded" value={String(graded)} note="against later filings" />
            <Kpi label="Accuracy, learning" value={learnedNow == null ? "n/a" : pct(learnedNow)} note={lift == null ? undefined : `${lift >= 0 ? "+" : ""}${lift} pts vs frozen twin`} accent="var(--success)" />
            <Kpi label="Average Brier score" value={brier == null ? "n/a" : brier.toFixed(2)} note="lower is better" />
          </section>

          <div role="tablist" aria-label="Analyst" className="grid gap-3 grid-cols-2 md:grid-cols-4">
            {data.map((d) => {
              const on = d.agent === sel?.agent;
              return (
                <button key={d.agent} role="tab" id={`tab-${d.agent}`} aria-selected={on} aria-controls="agent-panel" tabIndex={on ? 0 : -1}
                  onClick={() => go(mubitHref(d.agent))}
                  onKeyDown={(e) => {
                    const i = data.indexOf(d), n = data.length;
                    const j = e.key === "ArrowRight" ? (i + 1) % n : e.key === "ArrowLeft" ? (i + n - 1) % n : -1;
                    if (j >= 0) { e.preventDefault(); go(mubitHref(data[j].agent)); setTimeout(() => document.getElementById(`tab-${data[j].agent}`)?.focus(), 0); }
                  }}
                  className="card text-left p-4 cursor-pointer" style={{ color: "var(--foreground)", borderColor: on ? "var(--primary)" : undefined, background: on ? "var(--card-alt)" : undefined }}>
                  <div className="font-semibold">{d.investor}</div>
                  <div className="mute text-xs">{ROLE[d.agent] ?? d.agent} analyst</div>
                  <div className="num text-xl font-semibold mt-3">{d.accuracy == null ? "n/a" : pct(d.accuracy)}</div>
                  <div className="num text-xs mute truncate" title={d.model_version ?? undefined}>{d.model_version ?? "version n/a"}</div>
                </button>
              );
            })}
          </div>

          {sel && (
            <AnimatePresence mode="wait">
              <motion.div key={sel.agent} id="agent-panel" role="tabpanel" aria-labelledby={`tab-${sel.agent}`} tabIndex={0}
                initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: DUR.base }} className="grid gap-4 lg:grid-cols-[1.25fr_1fr] items-start">
                <AgentDetail d={sel} />
                <Story c={sel.last_correction ?? null} d={sel} />
              </motion.div>
            </AnimatePresence>
          )}
        </>
      )}

      <HeldOut />
      </>)}
    </div>
  );
}

const SEGMENTS = [["all_companies", "All companies"], ["seen_companies", "Seen in training"], ["unseen_companies", "Never seen"]] as const;
const acc = (s?: Score) => (s?.accuracy == null ? "n/a" : pct(s.accuracy));

/** The one-shot held-out test: quarters after training, scored once, learned against its frozen twin. */
function HeldOut() {
  const q = useQuery({ queryKey: ["heldout"], queryFn: api.heldout, retry: false });
  const [seg, setSeg] = useState<string>("all_companies");
  if (q.isLoading) return <Skeleton h={160} />;
  if (q.isError || !q.data) return null; // no report yet: nothing to show, nothing to claim
  const r: HeldOutReport = q.data.report;
  const [from, to] = r.split.held_out_window;
  return (
    <section className="card p-5" aria-label="Held-out test">
      <div className="flex items-center gap-3 flex-wrap">
        <h2 className="text-xl font-semibold m-0">Held-out test</h2>
        {r.banner && <StubChip />}
      </div>
      <p className="mute text-sm mt-1 mb-3 max-w-2xl">
        Quarters <span className="num">{from}</span> to <span className="num">{to}</span>, after training ended, scored once.
        {" "}{r.split.held_out_companies.length} {r.split.held_out_companies.length === 1 ? "company was" : "companies were"} never learned from. Only quarters where both the learning analyst
        and its frozen twin have a graded call are counted.
      </p>
      <div role="tablist" aria-label="Companies" className="flex gap-2 mb-3 flex-wrap">
        {SEGMENTS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={seg === k} onClick={() => setSeg(k)} className="chip cursor-pointer"
            style={{ borderColor: seg === k ? "var(--primary)" : undefined, color: seg === k ? "var(--foreground)" : undefined }}>{label}</button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm num">
          <thead className="mute text-xs text-left">
            <tr><th className="py-1 pr-4 font-normal">Analyst</th><th className="pr-4 font-normal">calls</th><th className="pr-4 font-normal">With lessons</th>
              <th className="pr-4 font-normal">Frozen twin</th><th className="pr-4 font-normal">difference</th><th className="pr-4 font-normal">Naive</th><th className="font-normal">Base rate</th></tr>
          </thead>
          <tbody>
            {Object.entries(r.agents).map(([agent, a]) => {
              const s = a.segments[seg];
              if (!s) return null;
              const d = s.learned_minus_frozen.accuracy;
              const naive = Object.entries(s.baselines).find(([k]) => k !== "base_rate")?.[1];
              return (
                <tr key={agent} className="border-t" style={{ borderColor: "var(--divider)" }}>
                  <td className="py-2 pr-4" style={{ fontFamily: "inherit" }}>{ROLE[agent] ?? agent}</td>
                  <td className="pr-4">{s.n}</td>
                  <td className="pr-4" style={{ color: "var(--success)" }}>{acc(s.learned)}</td>
                  <td className="pr-4">{acc(s.frozen)}</td>
                  <td className="pr-4" style={{ color: d == null ? undefined : d >= 0 ? "var(--success)" : "var(--error)" }}>
                    {d == null ? "n/a" : `${d >= 0 ? "+" : ""}${Math.round(d * 1000) / 10} pts`}</td>
                  <td className="pr-4">{acc(naive)}</td>
                  <td>{acc(s.baselines.base_rate)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Kpi({ label, value, note, accent }: { label: string; value: string; note?: string; accent?: string }) {
  return (
    <div className="card p-4">
      <div className="mute text-xs">{label}</div>
      <div className="num text-3xl font-semibold my-1" style={{ color: accent }}>{value}</div>
      {note && <div className="mute text-xs">{note}</div>}
    </div>
  );
}

function AgentDetail({ d }: { d: TrackRecord }) {
  const l = last(d.learned), f = last(d.frozen);
  return (
    <section className="card p-5" aria-label={`${d.investor} track record`}>
      <div className="flex items-center gap-2 flex-wrap">
        <h2 className="text-xl font-semibold m-0">{d.investor}</h2>
        <span className="chip num" title="Model version in force at this date">{d.model_version ?? "version n/a"}</span>
      </div>
      <div className="flex gap-8 mt-4 flex-wrap">
        <Stat label="recent accuracy" value={d.accuracy == null ? "n/a" : pct(d.accuracy)} />
        <Stat label="graded calls" value={String(d.calls_graded)} />
        <Stat label="corrections" value={String(d.corrections_applied)} />
        {d.brier != null && <Stat label="Brier score" value={d.brier.toFixed(2)} />}
      </div>
      <Curve d={d} />
      <div className="mute text-xs mt-2 flex gap-5 flex-wrap">
        <span style={{ color: "var(--success)" }}>With lessons{l != null && <span className="num"> {pct(l)}</span>}</span>
        <span>Frozen twin{f != null && <span className="num"> {pct(f)}</span>}</span>
        <span>Rolling accuracy by quarter</span>
      </div>
    </section>
  );
}

const Stat = ({ label, value }: { label: string; value: string }) => (
  <div><div className="num text-2xl font-semibold">{value}</div><div className="mute text-xs">{label}</div></div>
);

/** Learned vs frozen rolling accuracy on a fixed 0-100% axis; the gap between the lines is shaded. */
function Curve({ d }: { d: TrackRecord }) {
  const W = 640, H = 230, L = 38, R = 12, T = 12, B = 26;
  const n = d.learned.length;
  if (n < 2) return <p className="mute text-sm mt-4">Not enough history yet.</p>;
  const x = (i: number) => L + (i / (n - 1)) * (W - L - R);
  const y = (v: number) => T + (1 - v) * (H - T - B);
  const pts = (a: number[]) => a.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const fz = d.frozen.length === n ? d.frozen : null;
  const area = fz ? `${pts(d.learned)} ${[...fz].map((v, i) => `${x(i)},${y(v)}`).reverse().join(" ")}` : null;
  const yrs = d.quarters.map((q, i) => ({ q: q.slice(0, 4), i })).filter((o, k, a) => k === 0 || o.q !== a[k - 1].q);
  const desc = `Rolling accuracy over ${n} quarters. Learning analyst ends at ${pct(d.learned[n - 1])}${fz ? `, frozen twin ends at ${pct(fz[n - 1])}` : ""}.`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full mt-4" role="img" aria-label={desc}>
      {[0, 0.5, 1].map((g) => (
        <g key={g}><line x1={L} x2={W - R} y1={y(g)} y2={y(g)} stroke="var(--divider)" strokeDasharray={g === 0.5 ? "3 4" : undefined} />
          <text x={L - 6} y={y(g)} textAnchor="end" dominantBaseline="central" fontSize="11" fill="var(--muted)" className="num">{Math.round(g * 100)}%</text></g>
      ))}
      {yrs.map((o) => <text key={o.i} x={x(o.i)} y={H - 6} fontSize="11" fill="var(--muted)" textAnchor="middle" className="num">{o.q}</text>)}
      {area && <polygon points={area} fill="var(--success)" opacity="0.12" />}
      {fz && <polyline points={pts(fz)} fill="none" stroke="var(--muted)" strokeWidth="1.8" strokeDasharray="5 4" />}
      <motion.polyline points={pts(d.learned)} fill="none" stroke="var(--success)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: DUR.slower }} />
      <circle cx={x(n - 1)} cy={y(d.learned[n - 1])} r="4" fill="var(--success)" />
    </svg>
  );
}

/** The correction story: what was called, what happened, the lesson, and the version bump it produced. */
function Story({ c, d }: { c: Correction | null; d: TrackRecord }) {
  if (!c) return <section className="card p-5 mute text-sm">No wrong calls yet, so nothing to learn from at this date.</section>;
  return (
    <section className="card p-5" aria-label="What it learned">
      <h2 className="text-lg font-semibold m-0">What {d.investor} learned</h2>
      <p className="mute text-xs mt-1 mb-4">Latest correction, <span className="num">{c.as_of}</span></p>
      <ol className="list-none m-0 p-0 grid gap-4" style={{ borderLeft: "2px solid var(--divider)" }}>
        <Step k="The call">Predicted <b>{c.predicted ?? "n/a"}</b></Step>
        <Step k="What happened"><b>{c.actual ?? "n/a"}</b>{c.error_type ? <span className="mute"> ({c.error_type.replaceAll("_", " ")})</span> : null}</Step>
        <Step k="The lesson">{c.lesson ?? c.summary}</Step>
        <Step k="The update">
          <span className="num">{c.version_before ?? "n/a"} → {c.version_after ?? "pending"}</span>
          <div className="mute text-xs mt-1">Update ref <span className="num">{c.mubit_ref ?? "n/a"}</span></div>
        </Step>
        {c.reasked_answer && <Step k="Asked again after the update"><b>{c.reasked_answer}</b></Step>}
      </ol>
      {d.fallback_updater && <p className="mute text-xs mt-4 mb-0">Applied by the offline fallback updater, not live Mubit.</p>}
    </section>
  );
}
const Step = ({ k, children }: { k: string; children: React.ReactNode }) => (
  <li className="pl-4 relative">
    <span className="absolute w-2.5 h-2.5 rounded-full" style={{ left: -6, top: 6, background: "var(--primary)" }} aria-hidden />
    <div className="mute text-xs">{k}</div><div className="text-sm">{children}</div>
  </li>
);
