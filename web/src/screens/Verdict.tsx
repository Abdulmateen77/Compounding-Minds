import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { api, pct, type AgentView, type MubitState } from "../api/client";
import { ErrorBox, Skeleton, Spark, StubChip } from "../components/bits";
import { jumpTo, mubitHref } from "../route";
import {
  AGENTS, HEADLINE, METRICS, SIGNAL, bottomLine, certainty, humanize, longDate, metricLabel, metricValue, plainAnswer,
} from "../plain";

export default function Verdict({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  const q = useQuery({ queryKey: ["assessment", id], queryFn: () => api.assessment(id) });
  if (q.isLoading) return <div className="grid gap-4"><Skeleton h={200} /><div className="grid gap-3"><Skeleton /><Skeleton /></div></div>;
  if (q.isError || !q.data) return <div className="grid gap-3"><ErrorBox msg="Could not load this assessment." onRetry={() => q.refetch()} /><a className="btn ghost justify-self-start no-underline" href="#/">← Another company</a></div>;
  const a = q.data, H = HEADLINE[a.label], name = a.company.name, when = longDate(a.as_of);
  const settled = a.committee.filter((v) => v.correct != null);
  const right = settled.filter((v) => v.correct).length;
  const tone = a.label === "investable" ? "var(--green)" : a.label === "not_investable" ? "var(--red)" : "var(--amber)";

  return (
    <div className="grid gap-8">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <a className="btn ghost no-underline" href="#/">← Another company</a>
        <button className="btn ghost" onClick={() => { navigator.clipboard?.writeText(window.location.href).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); }); }}>
          {copied ? "Link copied" : "Copy link"}
        </button>
      </div>

      {/* 1. Where we are in time, and the bottom line */}
      <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card overflow-hidden">
        <div className="px-6 md:px-8 py-3 text-sm flex items-center gap-2 flex-wrap" style={{ background: "var(--panel2)", borderBottom: "1px solid var(--line)" }}>
          <span className="font-semibold">Back to {when}.</span>
          <span className="mute">Three AI analysts studied {name} using only the filings public on that day. Below is what they concluded, then what really happened.</span>
          {a.stub && <StubChip />}
        </div>
        <div className="p-6 md:p-8 grid gap-5">
          <div>
            <p className="mute m-0 text-sm">Does the evidence in {name}'s filings support investing?</p>
            <h1 className="text-3xl md:text-4xl font-bold tracking-tight mt-1 mb-2" style={{ color: tone }}>{H.text}</h1>
            <p className="m-0 text-base md:text-lg max-w-3xl leading-relaxed">{bottomLine(a.committee)}</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            {a.committee.map((v) => {
              const p = plainAnswer(v.agent, v.answer), S = SIGNAL[p.signal];
              return (
                <a key={v.agent} href={`#card-${v.agent}`} onClick={jumpTo(`card-${v.agent}`)} className="rounded-xl p-3 no-underline grid gap-1"
                  style={{ background: `color-mix(in srgb, ${S.color} 9%, transparent)`, border: `1px solid color-mix(in srgb, ${S.color} 35%, var(--line))`, color: "var(--text)" }}>
                  <span className="text-xs mute">{AGENTS[v.agent]?.topic ?? v.agent} · {v.investor}</span>
                  <span className="font-semibold">{p.text}</span>
                  <span className="text-xs" style={{ color: S.color }}>{S.word}</span>
                </a>
              );
            })}
          </div>
          <div className="flex items-center gap-x-6 gap-y-2 flex-wrap text-sm">
            <span><span className="font-semibold">{certainty(a.confidence)}</span> <span className="mute num">({pct(a.confidence)})</span></span>
            {settled.length > 0 && <span><span className="font-semibold">Checked against reality:</span> <span className="mute">{right} of {settled.length} predictions came true</span></span>}
          </div>
          <p className="mute text-xs m-0">A reading of business evidence in public filings, not advice to buy or sell. Every number here was computed in Python from SEC filings; the analysts only judge them.</p>
        </div>
      </motion.section>

      {/* 2. Each prediction, sealed on the day, opened later */}
      <section className="grid gap-4">
        <h2 className="text-xl font-semibold m-0">The three predictions, and what happened</h2>
        {a.committee.map((v, i) => <Prediction key={v.agent} v={v} m={a.mubit.find((x) => x.agent === v.agent)} when={when} delay={i * 0.06} />)}
      </section>

      {/* 3. The numbers, in words */}
      <section className="grid gap-3">
        <div>
          <h2 className="text-xl font-semibold m-0">The numbers they were given</h2>
          <p className="mute text-sm m-0 mt-1">As known on {when}. The line shows each figure's history up to that day.</p>
        </div>
        {a.metrics.length === 0 && <p className="mute text-sm">No metrics stored for this quarter.</p>}
        {groups(a.committee, a.metrics).map(([topic, cards]) => (
          <div key={topic} className="grid gap-2">
            <h3 className="text-sm font-semibold m-0 mt-2 mute">{topic}</h3>
            <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
              {cards.map((m) => (
                <div key={m.name} className="card p-4 grid gap-1" title={m.accessions?.[0] ? `SEC filing ${m.accessions[0]}` : "Computed in Python from stored filings"}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-medium">{metricLabel(m.name)}</span>
                    <span className="num text-lg font-semibold">{metricValue(m.name, m.value)}</span>
                  </div>
                  <span className="mute text-xs leading-snug">{METRICS[m.name]?.meaning}</span>
                  {m.trend.length > 1 && <Spark data={m.trend} w={200} h={30} />}
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>

      <a href={mubitHref()} className="card p-5 flex items-center justify-between gap-4 flex-wrap no-underline" style={{ color: "var(--text)" }}>
        <span>
          <span className="font-semibold block">How these analysts learn from their mistakes</span>
          <span className="mute text-sm">Every wrong prediction becomes a lesson the analyst reads next time. An identical copy that never learns runs alongside, so you can see whether the lessons help.</span>
        </span>
        <span className="chip" style={{ color: "var(--blue)", borderColor: "var(--blue)" }}>See the track records</span>
      </a>
    </div>
  );
}

function Prediction({ v, m, when, delay }: { v: AgentView; m?: MubitState; when: string; delay: number }) {
  const [open, setOpen] = useState(false);
  const p = plainAnswer(v.agent, v.answer), S = SIGNAL[p.signal];
  const reasons = v.reasoning.map(humanize);
  const verdict = v.correct == null ? null : v.correct
    ? { word: "Came true", color: "var(--green)", mark: "✓" }
    : { word: "Did not come true", color: "var(--red)", mark: "✗" };

  return (
    <motion.article id={`card-${v.agent}`} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }}
      className="card grid md:grid-cols-[1fr_minmax(220px,0.55fr)] overflow-hidden">
      <div className="p-5 md:p-6 grid gap-3 content-start">
        <div className="flex items-center gap-2 flex-wrap text-sm">
          <span className="font-semibold">{v.investor}</span>
          <span className="mute">on {AGENTS[v.agent]?.topic.toLowerCase() ?? v.agent}</span>
          {m && (
            <a href={mubitHref(v.agent)} className="chip no-underline" title="This analyst's full track record">
              {m.accuracy == null ? "no track record yet" : `right ${pct(m.accuracy)} of the time so far`}
              {m.corrections_applied > 0 && ` · learned from ${m.corrections_applied} mistakes`}
            </a>
          )}
        </div>
        <p className="m-0 mute">{AGENTS[v.agent]?.question ?? v.question}</p>
        <div className="flex items-baseline gap-3 flex-wrap">
          <span className="text-2xl font-bold">{p.text}</span>
          <span className="chip" style={{ color: S.color, borderColor: S.color }}>{S.word}</span>
          <span className="mute text-sm num">{pct(v.confidence)} sure</span>
        </div>
        <div className="grid gap-1 text-sm">
          <span className="font-medium">Why</span>
          <ul className="m-0 pl-5 grid gap-1">{(open ? reasons : reasons.slice(0, 2)).map((r) => <li key={r}>{r}</li>)}</ul>
          {reasons.length > 2 && (
            <button className="justify-self-start text-sm mt-1" style={{ color: "var(--blue)", background: "none", border: 0, padding: 0, cursor: "pointer" }}
              onClick={() => setOpen(!open)} aria-expanded={open}>
              {open ? "Show less" : `Show all ${reasons.length} reasons`}
            </button>
          )}
        </div>
        {v.evidence.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {v.evidence.map((e) => (
              <span key={e.metric} className="chip" title={e.accession ? `SEC filing ${e.accession}` : "Computed in Python from stored filings"}>
                {metricLabel(e.metric)} <span className="num" style={{ color: "var(--text)" }}>{metricValue(e.metric, e.value)}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="p-5 md:p-6 grid gap-2 content-start" style={{ background: "var(--panel2)", borderLeft: "1px dashed var(--line)" }}>
        <span className="text-xs mute">What actually happened</span>
        {verdict ? (
          <>
            <span className="text-xl font-bold flex items-center gap-2" style={{ color: verdict.color }}>
              <span aria-hidden className="inline-grid place-items-center w-7 h-7 rounded-full text-base" style={{ background: `color-mix(in srgb, ${verdict.color} 18%, transparent)` }}>{verdict.mark}</span>
              {verdict.word}
            </span>
            {v.what_happened && <p className="m-0 text-sm leading-relaxed">{v.what_happened}</p>}
            {v.resolved_on && <span className="mute text-xs">Settled by the filing of {longDate(v.resolved_on)}</span>}
          </>
        ) : (
          <>
            <span className="text-lg font-semibold mute">Not settled yet</span>
            <p className="m-0 text-sm mute">The filings that decide this were not in the replay yet, or the company did not report the figures needed to check it.</p>
          </>
        )}
        <span className="mute text-xs mt-auto">Predicted on {when}</span>
      </div>
    </motion.article>
  );
}

/** Metric cards grouped under the analyst topic that used them, in committee order. */
function groups(views: AgentView[], metrics: { name: string; value: number; trend: number[]; accessions?: string[] }[]) {
  const owner = new Map<string, string>();
  for (const v of views) for (const e of v.evidence) if (!owner.has(e.metric)) owner.set(e.metric, AGENTS[v.agent]?.topic ?? v.agent);
  const out = new Map<string, typeof metrics>(views.map((v) => [AGENTS[v.agent]?.topic ?? v.agent, []]));
  for (const m of metrics) {
    const t = owner.get(m.name) ?? "Other";
    out.set(t, [...(out.get(t) ?? []), m]);
  }
  return [...out.entries()].filter(([, cards]) => cards.length > 0);
}
