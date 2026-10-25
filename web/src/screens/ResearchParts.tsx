import { useState } from "react";
import { motion } from "framer-motion";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Spark } from "../components/bits";
import { Disclosure, Head } from "../components/Section";
import { Say } from "../components/Say";
import { useEffectiveLevel } from "../literacy";
import { researchHref } from "../route";
import {
  POINT_IN_TIME, TONE, fmtValue, longDate, monthYear, money, multiple, pctOf, year,
  type Figure, type Flag, type News, type Report, type Section,
} from "../research";

/* The pieces the five company pages are built from. Each shows one thing once; the page that owns the question decides where it goes. */

const CARDS_SHOWN = 6;     // figure cards a section shows before "Show all"
const NEWS_SHOWN = 3;

/** What a figure means, for the reader's level: explained for beginners and intermediates, the filing it came from for advanced readers. */
function Meaning({ text, sources }: { text: string; sources?: string[] }) {
  const level = useEffectiveLevel();
  if (level === "advanced") return sources?.length ? <span className="mute text-xs leading-snug">Source: {sources.join(", ")}</span> : null;
  return <span className="mute text-xs leading-snug"><Say>{text}</Say></span>;
}

function ToneChip({ tone }: { tone: Figure["tone"] }) {
  if (!tone) return null;
  const T = TONE[tone];
  return <span className="chip" style={{ color: T.color, borderColor: T.color }}>{T.word}</span>;
}

const allFigures = (sections: Section[]) => sections.flatMap((s) => s.figures).filter((f) => f.value != null);

/* ───────────────────────── overview ───────────────────────── */

/** What the company does, six headline figures and the tally of checks. */
export function Summary({ r }: { r: Report }) {
  const t = r.tally!;
  return (
    <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card p-5 md:p-6 grid gap-4" aria-label="The company in numbers">
      {r.plans?.about && (
        <div>
          <span className="text-xs mute">What it does, in its own words</span>
          <p className="m-0 mt-1 text-base md:text-lg leading-relaxed max-w-3xl">“<Say>{r.plans.about}</Say>”</p>
        </div>
      )}
      <div className="grid gap-3 grid-cols-2 md:grid-cols-3">
        {r.scorecard!.slice(0, 6).map((f) => {
          const color = f.tone ? TONE[f.tone].color : "var(--divider)";
          return (
            <div key={f.key} className="rounded-xl p-3 md:p-4 grid gap-1" style={{ background: `color-mix(in srgb, ${color} 8%, transparent)`, border: `1px solid color-mix(in srgb, ${color} 35%, var(--divider))` }}>
              <span className="text-xs mute"><Say>{f.label}</Say></span>
              <span className="num text-xl md:text-2xl font-semibold">{fmtValue(f.unit, f.value)}{f.approx ? " ≈" : ""}</span>
              <span className="text-xs" style={{ color }}>{f.tone ? TONE[f.tone].word : "context"}</span>
            </div>
          );
        })}
      </div>
      <p className="m-0 text-sm">
        Across {t.good + t.watch + t.warn} checks:{" "}
        <b style={{ color: "var(--success)" }}>{t.good} strengths</b>, <b style={{ color: "var(--warning)" }}>{t.watch} worth watching</b>, <b style={{ color: "var(--error)" }}>{t.warn} concerns</b>.
      </p>
    </motion.section>
  );
}

function Pick({ items, tone, empty }: { items: { label: string; value: string; meaning: string }[]; tone: "good" | "warn"; empty: string }) {
  const color = TONE[tone].color;
  return (
    <div className="card p-4 grid gap-3 content-start">
      <span className="font-semibold text-sm" style={{ color }}>{tone === "good" ? "What stands out well" : "What to look at closely"}</span>
      {items.length === 0 && <span className="mute text-sm">{empty}</span>}
      {items.map((i) => (
        <div key={i.label} className="grid gap-1">
          <span className="text-sm"><b><Say>{i.label}</Say></b> <span className="num">{i.value}</span></span>
          <Meaning text={i.meaning} />
        </div>
      ))}
    </div>
  );
}

/** The three strongest and three weakest things in the figures, so the overview says what matters without the full list. */
export function Highlights({ r }: { r: Report }) {
  const figs = allFigures(r.sections ?? []);
  const flags = (r.risk_flags ?? []).filter((f) => f.tone === "warn");
  const pick = (f: Figure) => ({ label: f.label, value: fmtValue(f.unit, f.value), meaning: f.meaning });
  const strengths = figs.filter((f) => f.tone === "good").slice(0, 3).map(pick);
  const concerns = [
    ...flags.map((f) => ({ label: f.label, value: f.detail, meaning: f.meaning })),
    ...figs.filter((f) => f.tone === "warn").map(pick),
    ...figs.filter((f) => f.tone === "watch").map(pick),
  ].slice(0, 3);
  return (
    <section className="grid gap-3" aria-label="What stands out">
      <div className="grid gap-3 md:grid-cols-2 items-start">
        <Pick items={strengths} tone="good" empty="No figure stands out as a clear strength." />
        <Pick items={concerns} tone="warn" empty="No figure raises a concern." />
      </div>
      <p className="m-0 text-sm"><a href={researchHref(r.company.cik, "financials")} className="underline underline-offset-4" style={{ color: "var(--primary)" }}>See every figure and risk check →</a></p>
    </section>
  );
}

export function NewsBlock({ n }: { n: News }) {
  const [all, setAll] = useState(false);
  const lines = n.lines, heads = n.articles;
  if (!lines.length && !heads.length) return null;
  const total = lines.length || heads.length;
  return (
    <section className="grid gap-3">
      <Head title="What has happened lately?" blurb={`Summarised by an AI from news articles found on ${longDate(n.retrieved)}. News is not part of the financial figures, so open the link before relying on it.`} />
      <div className="card p-5 grid gap-3">
        {lines.length > 0
          ? lines.slice(0, all ? undefined : NEWS_SHOWN).map((l) => (
              <div key={l.url} className="grid gap-1">
                <p className="m-0 text-sm leading-relaxed"><Say>{l.text}</Say></p>
                <a href={l.url} target="_blank" rel="noreferrer" className="text-xs underline" style={{ color: "var(--primary)" }}>{l.source}{l.age ? `, ${l.age}` : ""}: {l.title}</a>
              </div>
            ))
          : heads.slice(0, all ? undefined : NEWS_SHOWN).map((a) => (
              <a key={a.url} href={a.url} target="_blank" rel="noreferrer" className="text-sm underline" style={{ color: "var(--primary)" }}>{a.source}{a.age ? `, ${a.age}` : ""}: {a.title}</a>
            ))}
        {total > NEWS_SHOWN && <button className="btn ghost justify-self-start" onClick={() => setAll((x) => !x)}>{all ? "Show fewer" : `Show all ${total}`}</button>}
      </div>
    </section>
  );
}

/* ───────────────────────── the page header ───────────────────────── */

/** One line saying which filing the figures come from. The long form (and the caveat about the feed lagging) is on the Sources page. */
export function DataSource({ r, full = false }: { r: Report; full?: boolean }) {
  const lf = r.latest_filing, through = r.data_through!;
  const behind = lf && r.facts_through && r.facts_through < lf.filed;
  if (!full) {
    return (
      <p className="m-0 mute text-xs">
        Figures: 12 months to {longDate(through)}{lf && !behind && <>, from its {lf.form} filed {longDate(lf.filed)}</>} · SEC EDGAR, checked {r.checked_at ? longDate(r.checked_at) : "today"}
        {behind && <span style={{ color: "var(--warning)" }}> · its newest filing is not in the SEC's data feed yet</span>}
        {" · "}<a href={researchHref(r.company.cik, "sources")} className="underline underline-offset-4">sources</a>
      </p>
    );
  }
  return (
    <div className="rounded-xl px-4 py-3 text-sm grid gap-1" style={{ background: "var(--card-alt)", border: "1px solid var(--divider)" }}>
      <span>
        <b>Latest figures: the 12 months to {longDate(through)}</b>
        {lf && !behind && <>, from {r.company.name}'s {lf.form} filed with the SEC on {longDate(lf.filed)}</>}.
        {" "}Source: SEC EDGAR, checked {r.checked_at ? longDate(r.checked_at) : "today"}.
      </span>
      {behind && <span style={{ color: "var(--warning)" }}>Its newest filing ({lf!.form}, filed {longDate(lf!.filed)}) is not in the SEC's data feed yet, so these figures stop at the filing before it.</span>}
    </div>
  );
}

/* ───────────────────────── financials ───────────────────────── */

export function TrendChart({ sections }: { sections: Section[] }) {
  const fig = (k: string) => sections.flatMap((s) => s.figures).find((f) => f.key === k);
  const rev = fig("revenue"), ebitda = fig("ebitda") ?? fig("net_income"), fcf = fig("fcf");
  if (!rev || rev.history.length < 2) return null;
  const rows = rev.history.map((h, i) => ({
    year: year(h.end), Revenue: h.value, [ebitda?.label ?? "Profit"]: ebitda?.history[i]?.value ?? null, "Free cash flow": fcf?.history[i]?.value ?? null,
  }));
  const series = [["Revenue", "var(--primary)"], [ebitda?.label ?? "Profit", "var(--secondary)"], ["Free cash flow", "var(--success)"]] as const;
  return (
    <section className="card p-5 grid gap-2">
      <Head title="The last six years at a glance" blurb="Twelve-month totals at each year's latest report." />
      <div style={{ height: 260 }}>
        <ResponsiveContainer>
          <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--divider)" vertical={false} />
            <XAxis dataKey="year" stroke="var(--muted)" fontSize={12} />
            <YAxis stroke="var(--muted)" fontSize={12} tickFormatter={(v) => money(v, 0)} width={64} />
            <Tooltip formatter={(v) => money(Number(v))} contentStyle={{ background: "var(--card)", border: "1px solid var(--divider)", borderRadius: 12 }} />
            <Legend />
            {series.map(([k, c]) => <Bar key={k} dataKey={k} fill={c} radius={[4, 4, 0, 0]} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function toneCounts(figs: Figure[]) {
  const n = (t: Figure["tone"]) => figs.filter((f) => f.tone === t).length;
  const g = n("good"), w = n("watch"), c = n("warn");
  return [g && `${g} strength${g === 1 ? "" : "s"}`, w && `${w} to watch`, c && `${c} concern${c === 1 ? "" : "s"}`].filter(Boolean).join(", ");
}

/** A financial section: closed it shows its three leading figures, open it shows the reading and the figure cards. */
export function FinSection({ s, through, defaultOpen = false }: { s: Section; through: string; defaultOpen?: boolean }) {
  const [all, setAll] = useState(false);
  const shown = s.figures.filter((f) => f.value != null);
  if (shown.length === 0) return null;
  const lead = shown.slice(0, 3).map((f) => `${f.label} ${fmtValue(f.unit, f.value)}`).join("  ·  ");
  const cards = all ? shown : shown.slice(0, CARDS_SHOWN);
  return (
    <Disclosure title={s.title} count={toneCounts(shown) || undefined} summary={<span className="num">{lead}</span>} defaultOpen={defaultOpen}>
      {s.reading.length > 0 && <p className="m-0 max-w-3xl leading-relaxed text-sm"><Say>{s.reading.join(" ")}</Say></p>}
      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">{cards.map((f) => <FigureCard key={f.key} f={f} through={through} />)}</div>
      {shown.length > CARDS_SHOWN && <button className="btn ghost justify-self-start" onClick={() => setAll((x) => !x)}>{all ? "Show fewer" : `Show all ${shown.length}`}</button>}
    </Disclosure>
  );
}

function FigureCard({ f, through }: { f: Figure; through: string }) {
  const h = f.history.filter((x) => x.value != null);
  const when = POINT_IN_TIME.has(f.key) ? `on ${longDate(through)}` : `12 months to ${longDate(through)}`;
  return (
    <div className="rounded-xl p-4 grid gap-1 content-start" style={{ background: "var(--card-alt)" }} title={f.sources.length ? `From SEC filings: ${f.sources.join(", ")}` : undefined}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium"><Say>{f.label}</Say></span>
        <ToneChip tone={f.tone} />
      </div>
      <span className="num text-2xl font-semibold">{fmtValue(f.unit, f.value)}{f.approx && <span className="mute text-sm" title="Approximate: see the notes on the Sources page"> ≈</span>}</span>
      <span className="text-xs mute">{when}</span>
      <Meaning text={f.meaning} sources={f.sources} />
      {h.length > 2 && (
        <div className="mt-1">
          <Spark data={h.map((x) => x.value as number)} w={220} h={34} />
          <div className="flex justify-between mute text-xs num">
            <span>{monthYear(h[0].end)}: {fmtValue(f.unit, h[0].value)}</span>
            <span>{monthYear(h[h.length - 1].end)}: {fmtValue(f.unit, h[h.length - 1].value)}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export function RiskChecks({ flags }: { flags: Flag[] }) {
  if (!flags.length) return null;
  const bad = flags.filter((f) => f.tone === "warn").length, watch = flags.filter((f) => f.tone === "watch").length;
  const summary = bad || watch ? [bad && `${bad} concern${bad === 1 ? "" : "s"}`, watch && `${watch} to watch`].filter(Boolean).join(", ") : "No risk check raises a concern";
  return (
    <Disclosure title="Could it get into trouble?" count={`${flags.length} checks`} summary={`The checks Charlie Munger asks first: how could this business fail? ${summary}.`} defaultOpen={bad > 0}>
      <div className="grid gap-3 md:grid-cols-2">
        {flags.map((f) => {
          const T = f.tone ? TONE[f.tone] : null;
          return (
            <div key={f.key} className="rounded-xl p-4 flex items-start gap-3" style={{ background: "var(--card-alt)" }} title={f.sources.length ? `From SEC filings: ${f.sources.join(", ")}` : undefined}>
              <span aria-hidden className="inline-grid place-items-center w-7 h-7 rounded-full shrink-0 text-sm" style={{ background: `color-mix(in srgb, ${T?.color ?? "var(--muted)"} 20%, transparent)`, color: T?.color }}>{f.tone === "good" ? "✓" : f.tone === "warn" ? "!" : "•"}</span>
              <div className="grid gap-1">
                <span className="font-medium text-sm"><Say>{f.label}</Say>: <span style={{ color: T?.color }}>{f.detail}</span></span>
                <Meaning text={f.meaning} sources={f.sources} />
              </div>
            </div>
          );
        })}
      </div>
    </Disclosure>
  );
}

/* ───────────────────────── value and outlook ───────────────────────── */

export function MarketBlock({ m }: { m: NonNullable<Report["market"]> }) {
  const lo = m.low_52w, hi = m.high_52w;
  const pos = lo != null && hi != null && hi > lo ? Math.min(Math.max((m.price - lo) / (hi - lo), 0), 1) : null;
  const rows: [string, string, string][] = m.market_cap == null ? [] : [
    ["Market value", money(m.market_cap), "What the whole company is worth at today's share price"],
    ["Price to earnings", multiple(m.pe), "Share price per dollar of yearly profit"],
    ["Enterprise value to EBITDA", multiple(m.ev_to_ebitda), "Company value, including its debt, per dollar of cash earnings"],
    ["Price to sales", multiple(m.price_to_sales), "Market value per dollar of yearly sales"],
    ["Free-cash-flow yield", pctOf(m.fcf_yield), "Free cash flow as a share of market value"],
    ["Dividend yield", m.dividend_yield == null ? "none paid" : pctOf(m.dividend_yield), "Cash dividends as a share of market value"],
  ];
  return (
    <section className="grid gap-3">
      <Head title="What does the market charge for it?" blurb="What investors pay today, not where the price is going." />
      <div className="card p-5 grid gap-4">
        <div className="flex items-baseline gap-3 flex-wrap">
          <span className="num text-3xl font-semibold">{m.currency === "USD" ? "$" : ""}{m.price.toFixed(2)}</span>
          <span className="mute text-sm">share price on {longDate(m.price_date)}</span>
        </div>
        {pos != null && (
          <div className="max-w-md">
            <div className="relative h-2 rounded-full" style={{ background: "var(--divider)" }}><span className="absolute top-1/2 w-3 h-3 rounded-full" style={{ left: `calc(${pos * 100}% - 6px)`, transform: "translateY(-50%)", background: "var(--primary)" }} /></div>
            <div className="flex justify-between text-xs mute num mt-1"><span>52-week low {lo!.toFixed(2)}</span><span>high {hi!.toFixed(2)}</span></div>
          </div>
        )}
        {m.history.length > 2 && <Spark data={m.history.map((h) => h.close)} w={420} h={50} />}
        {rows.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
            {rows.map(([l, v, t]) => (
              <div key={l} className="grid gap-1"><span className="text-xs mute"><Say>{l}</Say></span><span className="num text-lg font-semibold">{v}</span><Meaning text={t} /></div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

/** What management says, quoted once: strategy, what it builds, what it expects. */
export function Plans({ p }: { p: NonNullable<Report["plans"]> }) {
  const groups: [string, string[]][] = [["Its plans and priorities", p.strategy], ["What it is researching and building", p.rnd], ["What management expects", p.outlook]];
  const live = groups.filter(([, s]) => s.length);
  if (!live.length) return null;
  const n = live.reduce((t, [, s]) => t + s.length, 0);
  return (
    <Disclosure title="What does the company say about its future?" count={`${n} quotes`}
      summary={`Quoted word for word from its annual report filed ${longDate(p.source.filed)}.`}>
      <p className="mute text-sm m-0">From its annual report filed {longDate(p.source.filed)}. <a href={p.source.url} target="_blank" rel="noreferrer" className="underline">Read the filing</a></p>
      <div className="grid gap-3 md:grid-cols-3">
        {live.map(([title, items]) => (
          <div key={title} className="rounded-xl p-4 grid gap-3 content-start" style={{ background: "var(--card-alt)" }}>
            <span className="font-semibold text-sm">{title}</span>
            {items.map((t) => <blockquote key={t} className="m-0 pl-3 text-sm leading-relaxed" style={{ borderLeft: "4px solid var(--primary)" }}><Say>{t}</Say></blockquote>)}
          </div>
        ))}
      </div>
    </Disclosure>
  );
}
