import { useQueries, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { api, pct, type Correction, type TrackRecord } from "../api/client";
import { ErrorBox, Skeleton, StubChip } from "../components/bits";
import { go, mubitHref } from "../route";

const AGENTS = ["fundamentals", "risk", "scenarios"] as const; // the MVP committee; Valuation is a stretch agent
const ROLE: Record<string, string> = { fundamentals: "Fundamentals", valuation: "Valuation", risk: "Risk", scenarios: "Scenarios" };
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

  return (
    <div className="grid gap-6">
      <div>
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight m-0">Mubit: how the analysts learn</h1>
          {health.data?.stub !== false && <StubChip />}
        </div>
        <p className="mute mt-2 mb-0 max-w-2xl">Every wrong call becomes a correction, and Mubit turns corrections into a new model version. Each analyst here is compared with a frozen twin that never updates.{asOf && <> Figures run to <span className="num">{asOf}</span>.</>}</p>
      </div>

      {failed && <ErrorBox msg="Could not load track records. Is the API running?" onRetry={() => qs.forEach((q) => q.refetch())} />}
      {loading && <div className="grid gap-3 grid-cols-2 md:grid-cols-4"><Skeleton h={96} /><Skeleton h={96} /><Skeleton h={96} /><Skeleton h={96} /></div>}

      {data.length > 0 && (
        <>
          <section aria-label="Summary" className="grid gap-3 grid-cols-2 md:grid-cols-4">
            <Kpi label="Corrections applied" value={String(corrections)} note="across all analysts" />
            <Kpi label="Calls graded" value={String(graded)} note="against later filings" />
            <Kpi label="Accuracy, learning" value={learnedNow == null ? "n/a" : pct(learnedNow)} note={lift == null ? undefined : `${lift >= 0 ? "+" : ""}${lift} pts vs frozen twin`} accent="var(--green)" />
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
                  className="card text-left p-4 cursor-pointer" style={{ color: "var(--text)", borderColor: on ? "var(--blue)" : undefined, background: on ? "var(--panel2)" : undefined }}>
                  <div className="font-semibold">{d.investor}</div>
                  <div className="mute text-xs">{ROLE[d.agent] ?? d.agent} analyst</div>
                  <div className="num text-xl font-semibold mt-3">{d.accuracy == null ? "n/a" : pct(d.accuracy)}</div>
                  <div className="num text-[11px] mute truncate" title={d.model_version ?? undefined}>{d.model_version ?? "version n/a"}</div>
                </button>
              );
            })}
          </div>

          {sel && (
            <AnimatePresence mode="wait">
              <motion.div key={sel.agent} id="agent-panel" role="tabpanel" aria-labelledby={`tab-${sel.agent}`} tabIndex={0}
                initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }} className="grid gap-4 lg:grid-cols-[1.25fr_1fr] items-start">
                <AgentDetail d={sel} />
                <Story c={sel.last_correction ?? null} d={sel} />
              </motion.div>
            </AnimatePresence>
          )}
        </>
      )}
    </div>
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
        <span style={{ color: "var(--green)" }}>Learns with Mubit{l != null && <span className="num"> {pct(l)}</span>}</span>
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
        <g key={g}><line x1={L} x2={W - R} y1={y(g)} y2={y(g)} stroke="var(--line)" strokeDasharray={g === 0.5 ? "3 4" : undefined} />
          <text x={L - 6} y={y(g)} textAnchor="end" dominantBaseline="central" fontSize="11" fill="var(--mute)" className="num">{Math.round(g * 100)}%</text></g>
      ))}
      {yrs.map((o) => <text key={o.i} x={x(o.i)} y={H - 6} fontSize="11" fill="var(--mute)" textAnchor="middle" className="num">{o.q}</text>)}
      {area && <polygon points={area} fill="var(--green)" opacity="0.12" />}
      {fz && <polyline points={pts(fz)} fill="none" stroke="var(--mute)" strokeWidth="1.8" strokeDasharray="5 4" />}
      <motion.polyline points={pts(d.learned)} fill="none" stroke="var(--green)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1 }} />
      <circle cx={x(n - 1)} cy={y(d.learned[n - 1])} r="4" fill="var(--green)" />
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
      <ol className="list-none m-0 p-0 grid gap-4" style={{ borderLeft: "2px solid var(--line)" }}>
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
    <span className="absolute w-2.5 h-2.5 rounded-full" style={{ left: -6, top: 6, background: "var(--blue)" }} aria-hidden />
    <div className="mute text-xs">{k}</div><div className="text-sm">{children}</div>
  </li>
);
