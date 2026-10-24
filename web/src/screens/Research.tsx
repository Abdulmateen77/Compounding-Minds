import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ErrorBox, Skeleton, Spark } from "../components/bits";
import { researchHref, go } from "../route";
import { EvidencePanel, Future, Lenses, Verdict, Worth } from "./ResearchAnalysis";
import {
  TONE, fmtValue, longDate, money, multiple, pctOf, year,
  type Candidate, type Figure, type Flag, type News, type Report, type SearchResult, type Section,
} from "../research";

const j = async <T,>(url: string): Promise<T> => {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText);
  return r.json();
};

export default function Research({ cik }: { cik?: string }) {
  return cik ? <ReportPage cik={cik} /> : <Landing />;
}

/* ───────────────────────── landing: one question, one box ───────────────────────── */

const EXAMPLES = ["Tesla", "Apple", "Coca-Cola", "Nvidia", "Walmart"];

function Landing() {
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 220); return () => clearTimeout(t); }, [q]);
  const s = useQuery({ queryKey: ["rsearch", debounced], enabled: debounced.length >= 2, queryFn: () => j<SearchResult>(`/api/research/search?q=${encodeURIComponent(debounced)}`) });
  const pick = (c: Candidate) => go(researchHref(c.cik));

  return (
    <div className="grid gap-10">
      <section className="card p-6 md:p-10 grid gap-6" style={{ background: "linear-gradient(135deg, color-mix(in srgb, var(--blue) 10%, var(--panel)), var(--panel))" }}>
        <div className="max-w-2xl grid gap-3">
          <h1 className="text-3xl md:text-5xl font-bold tracking-tight m-0 leading-tight">Is this company worth your money? Check the filings.</h1>
          <p className="m-0 text-base md:text-lg leading-relaxed mute">
            Type a company name or ticker. We read its official SEC filings, work out the numbers, and show what a careful investor would look at: growth, profit, cash, debt, what it spends on the future, and what it says about its own plans.
          </p>
        </div>

        <div className="max-w-2xl relative">
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} aria-label="Company name or ticker"
            onKeyDown={(e) => { if (e.key === "Enter" && s.data?.results[0]) pick(s.data.results[0]); }}
            placeholder="Company name or ticker, for example Tesla or TSLA"
            className="card w-full px-5 py-4 text-lg outline-none" style={{ color: "var(--text)", borderColor: "var(--blue)" }} />
          {debounced.length >= 2 && (
            <div className="card absolute left-0 right-0 mt-2 z-20 overflow-hidden" role="listbox" style={{ boxShadow: "0 12px 40px rgba(0,0,0,.25)" }}>
              {s.isLoading && <div className="p-4 mute text-sm">Searching the SEC company list…</div>}
              {s.isError && <div className="p-4 text-sm" style={{ color: "var(--red)" }}>Could not reach the search. Is the API running?</div>}
              {s.data?.results.map((c) => (
                <button key={c.cik} role="option" aria-selected={false} onClick={() => pick(c)}
                  className="w-full text-left px-5 py-3 flex items-center justify-between gap-3 cursor-pointer bg-transparent border-0"
                  style={{ color: "var(--text)", borderBottom: "1px solid var(--line)" }}>
                  <span><span className="font-semibold">{c.name}</span> <span className="num mute text-sm">{c.ticker}</span></span>
                  <span className="chip">{c.exchange ?? "US"} · United States</span>
                </button>
              ))}
              {s.data && s.data.results.length === 0 && <div className="p-4 text-sm">{s.data.message}</div>}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 flex-wrap text-sm">
          <span className="mute">Try</span>
          {EXAMPLES.map((e) => <button key={e} className="chip cursor-pointer bg-transparent" onClick={() => setQ(e)}>{e}</button>)}
        </div>
        <p className="mute text-xs m-0">Covers companies listed in the United States (NYSE and Nasdaq). London and European listings are coming.</p>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {[
          ["1", "It reads the filings", "Every figure comes from the company's own 10-K and 10-Q reports filed with the SEC, worked out by code, not guessed by an AI."],
          ["2", "It asks the investor's questions", "Is the business growing? Does profit turn into cash? Is the balance sheet safe? What is it investing in, and what does that earn?"],
          ["3", "It shows its working", "Each number lists the filing it came from. What the company says about its plans is quoted word for word, with a link to the page."],
        ].map(([n, h, t]) => (
          <div key={n} className="card p-5 grid gap-2 content-start">
            <span className="num inline-grid place-items-center w-7 h-7 rounded-full text-sm" style={{ background: "var(--blue)", color: "#fff" }}>{n}</span>
            <span className="font-semibold">{h}</span>
            <span className="mute text-sm leading-relaxed">{t}</span>
          </div>
        ))}
      </section>

      <p className="text-sm mute m-0">
        Want to know how accurate the AI analysts have been? <a href="#/past" className="underline underline-offset-4">See the past test</a> and the <a href="#/mubit" className="underline underline-offset-4">track record</a>.
      </p>
    </div>
  );
}

/* ───────────────────────── the report ───────────────────────── */

const STEPS = ["Finding the company's filings", "Reading the financial statements", "Reading the annual report for plans and R&D", "Reading the latest news and checking the share price"];

function Loading({ name }: { name?: string }) {
  const [i, setI] = useState(0);
  useEffect(() => { const t = setInterval(() => setI((x) => Math.min(x + 1, STEPS.length - 1)), 4500); return () => clearInterval(t); }, []);
  return (
    <div className="card p-8 grid gap-4" role="status">
      <h1 className="text-2xl font-bold m-0">Researching {name ?? "the company"}…</h1>
      <ol className="m-0 p-0 list-none grid gap-2 text-sm">
        {STEPS.map((s, k) => (
          <li key={s} className="flex items-center gap-3" style={{ opacity: k <= i ? 1 : 0.35 }}>
            <span aria-hidden className="inline-grid place-items-center w-5 h-5 rounded-full text-xs" style={{ background: k < i ? "var(--green)" : "var(--panel2)", color: k < i ? "#06210f" : "var(--mute)" }}>{k < i ? "✓" : k === i ? "…" : ""}</span>
            {s}
          </li>
        ))}
      </ol>
      <p className="mute text-sm m-0">The first lookup takes 20 to 30 seconds: it reads the filings, the annual report and the latest news. Later ones are instant.</p>
      <Skeleton h={80} />
    </div>
  );
}

function ReportPage({ cik }: { cik: string }) {
  const [copied, setCopied] = useState(false);
  const q = useQuery({ queryKey: ["report", cik], queryFn: () => j<Report>(`/api/research/company/${cik}`), staleTime: 10 * 60_000, retry: 0 });
  if (q.isLoading) return <Loading />;
  if (q.isError || !q.data) return <div className="grid gap-3"><ErrorBox msg={String(q.error ?? "Could not build the report.")} onRetry={() => q.refetch()} /><a className="btn ghost justify-self-start no-underline" href="#/">← Search again</a></div>;
  const r = q.data, c = r.company;

  if (!r.supported) {
    return (
      <div className="grid gap-4">
        <a className="btn ghost justify-self-start no-underline" href="#/">← Search again</a>
        <div className="card p-6 grid gap-2">
          <h1 className="text-2xl font-bold m-0">{c.name} {c.ticker && <span className="mute num text-lg">{c.ticker}</span>}</h1>
          <p className="m-0">{r.reason}</p>
          <p className="mute text-sm m-0">If this is a UK or European company, that market is not covered yet.</p>
        </div>
      </div>
    );
  }

  const sections = r.sections!, byId = (id: string) => sections.find((s) => s.id === id)!;
  return (
    <div className="grid gap-10">
      <header className="grid gap-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <a className="btn ghost no-underline" href="#/">← Search again</a>
          <div className="flex gap-2">
            <button className="btn ghost" onClick={() => { navigator.clipboard?.writeText(window.location.href).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); }); }}>{copied ? "Link copied" : "Copy link"}</button>
            <button className="btn ghost" onClick={() => { fetch(`/api/research/company/${cik}?refresh=true`).then(() => q.refetch()); }}>Refresh data</button>
          </div>
        </div>
        <div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight m-0">{c.name}</h1>
          <p className="mute m-0 mt-1 text-sm">
            <span className="num">{c.ticker}</span> · {c.exchange} · United States · financial data through {longDate(r.data_through!)}
          </p>
        </div>
      </header>

      {r.analysis && <Verdict a={r.analysis} name={c.name} />}
      <Summary r={r} />
      {r.news && <NewsBlock n={r.news} />}
      <TrendChart sections={sections} />

      {(["growth", "profit", "cash", "balance", "reinvest"] as const).map((id) => <SectionBlock key={id} s={byId(id)} />)}

      <RiskChecks flags={r.risk_flags ?? []} />
      {r.plans && <Plans p={r.plans} />}
      {r.market && <MarketBlock m={r.market} />}
      {r.analysis && <Lenses lenses={r.analysis.lenses} />}
      {r.analysis && <Worth a={r.analysis} />}
      {r.analysis?.future && <Future a={r.analysis} outlook={r.plans?.outlook ?? []} />}
      {r.analysis && <EvidencePanel />}
      {r.economy && r.economy.length > 0 && (
        <section className="grid gap-3">
          <div><h2 className="text-xl font-semibold m-0">What is the economy doing?</h2><p className="mute text-sm m-0 mt-1">Context for how this company's sales might move. As reported to date.</p></div>
          <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
            {r.economy.map((e) => (
              <div key={e.key} className="card p-4 grid gap-1">
                <div className="flex items-baseline justify-between gap-2"><span className="text-sm font-medium">{e.label}</span><span className="num text-lg font-semibold">{fmtValue(e.unit, e.value)}</span></div>
                <span className="mute text-xs">{e.meaning}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <footer className="grid gap-2 text-xs mute">
        {(r.notes ?? []).map((n) => <p key={n} className="m-0">Note: {n}</p>)}
        {(r.missing ?? []).length > 0 && <p className="m-0">Not reported in its filings: {r.missing!.join(", ")}.</p>}
        <p className="m-0">Every figure is computed from the company's SEC filings and lists the filing it came from. <a href={r.sec_url} target="_blank" rel="noreferrer" className="underline">See its filings on EDGAR</a>. Good, watch and concern labels are rules of thumb that describe the evidence; they are not advice. Research tool, not financial advice.</p>
      </footer>
    </div>
  );
}

/* ───────────────────────── pieces ───────────────────────── */

function ToneChip({ tone }: { tone: Figure["tone"] }) {
  if (!tone) return null;
  const T = TONE[tone];
  return <span className="chip" style={{ color: T.color, borderColor: T.color }}>{T.word}</span>;
}

function Summary({ r }: { r: Report }) {
  const t = r.tally!;
  return (
    <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card p-6 md:p-8 grid gap-5">
      {r.plans?.about && (
        <div>
          <span className="text-xs mute">What it does, in its own words</span>
          <p className="m-0 mt-1 text-lg leading-relaxed max-w-3xl">“{r.plans.about}”</p>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
        {r.scorecard!.map((f) => {
          const color = f.tone ? TONE[f.tone].color : "var(--line)";
          return (
            <div key={f.key} className="rounded-xl p-4 grid gap-1" style={{ background: `color-mix(in srgb, ${color} 8%, transparent)`, border: `1px solid color-mix(in srgb, ${color} 35%, var(--line))` }}>
              <span className="text-xs mute">{f.label}</span>
              <span className="num text-2xl font-semibold">{fmtValue(f.unit, f.value)}{f.approx ? " ≈" : ""}</span>
              <span className="text-xs" style={{ color }}>{f.tone ? TONE[f.tone].word : "context"}</span>
            </div>
          );
        })}
      </div>
      <p className="m-0 text-sm">
        Across {t.good + t.watch + t.warn} checks:{" "}
        <b style={{ color: "var(--green)" }}>{t.good} strengths</b>, <b style={{ color: "var(--amber)" }}>{t.watch} worth watching</b>, <b style={{ color: "var(--red)" }}>{t.warn} concerns</b>.
        <span className="mute"> Rules of thumb on the evidence, not advice.</span>
      </p>
    </motion.section>
  );
}

function TrendChart({ sections }: { sections: Section[] }) {
  const fig = (k: string) => sections.flatMap((s) => s.figures).find((f) => f.key === k);
  const rev = fig("revenue"), ebitda = fig("ebitda") ?? fig("net_income"), fcf = fig("fcf");
  if (!rev || rev.history.length < 2) return null;
  const rows = rev.history.map((h, i) => ({
    year: year(h.end), Revenue: h.value, [ebitda?.label ?? "Profit"]: ebitda?.history[i]?.value ?? null, "Free cash flow": fcf?.history[i]?.value ?? null,
  }));
  const series = [["Revenue", "var(--blue)"], [ebitda?.label ?? "Profit", "var(--purple)"], ["Free cash flow", "var(--green)"]] as const;
  return (
    <section className="card p-5 grid gap-2">
      <div><h2 className="text-xl font-semibold m-0">The last six years at a glance</h2><p className="mute text-sm m-0 mt-1">Twelve-month totals at each year's latest report.</p></div>
      <div style={{ height: 280 }}>
        <ResponsiveContainer>
          <BarChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="year" stroke="var(--mute)" fontSize={12} />
            <YAxis stroke="var(--mute)" fontSize={12} tickFormatter={(v) => money(v, 0)} width={64} />
            <Tooltip formatter={(v) => money(Number(v))} contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 12 }} />
            <Legend />
            {series.map(([k, c]) => <Bar key={k} dataKey={k} fill={c} radius={[4, 4, 0, 0]} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function SectionBlock({ s }: { s: Section }) {
  const shown = s.figures.filter((f) => f.value != null);
  if (shown.length === 0) return null;
  return (
    <section className="grid gap-3">
      <div>
        <h2 className="text-xl font-semibold m-0">{s.title}</h2>
        {s.reading.length > 0 && <p className="m-0 mt-2 max-w-3xl leading-relaxed">{s.reading.join(" ")}</p>}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">{shown.map((f) => <FigureCard key={f.key} f={f} />)}</div>
    </section>
  );
}

function FigureCard({ f }: { f: Figure }) {
  const h = f.history.filter((x) => x.value != null);
  return (
    <div className="card p-4 grid gap-1 content-start" title={f.sources.length ? `From SEC filings: ${f.sources.join(", ")}` : undefined}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium">{f.label}</span>
        <ToneChip tone={f.tone} />
      </div>
      <span className="num text-2xl font-semibold">{fmtValue(f.unit, f.value)}{f.approx && <span className="mute text-sm" title="Approximate: see the notes at the bottom"> ≈</span>}</span>
      <span className="mute text-xs leading-snug">{f.meaning}</span>
      {h.length > 2 && (
        <div className="mt-1">
          <Spark data={h.map((x) => x.value as number)} w={220} h={34} />
          <div className="flex justify-between mute text-[10px] num"><span>{year(h[0].end)}: {fmtValue(f.unit, h[0].value)}</span><span>{year(h[h.length - 1].end)}</span></div>
        </div>
      )}
    </div>
  );
}

function RiskChecks({ flags }: { flags: Flag[] }) {
  if (!flags.length) return null;
  return (
    <section className="grid gap-3">
      <div><h2 className="text-xl font-semibold m-0">Could it get into trouble?</h2><p className="mute text-sm m-0 mt-1">The checks Charlie Munger asks first: how could this business fail?</p></div>
      <div className="grid gap-3 md:grid-cols-2">
        {flags.map((f) => {
          const T = f.tone ? TONE[f.tone] : null;
          return (
            <div key={f.key} className="card p-4 flex items-start gap-3" title={f.sources.length ? `From SEC filings: ${f.sources.join(", ")}` : undefined}>
              <span aria-hidden className="inline-grid place-items-center w-7 h-7 rounded-full shrink-0 text-sm" style={{ background: `color-mix(in srgb, ${T?.color ?? "var(--mute)"} 20%, transparent)`, color: T?.color }}>{f.tone === "good" ? "✓" : f.tone === "warn" ? "!" : "•"}</span>
              <div className="grid gap-0.5">
                <span className="font-medium text-sm">{f.label}: <span style={{ color: T?.color }}>{f.detail}</span></span>
                <span className="mute text-xs">{f.meaning}</span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Plans({ p }: { p: NonNullable<Report["plans"]> }) {
  const groups: [string, string[]][] = [["Its plans and priorities", p.strategy], ["What it is researching and building", p.rnd], ["What management expects", p.outlook]];
  const any = groups.some(([, s]) => s.length);
  if (!any) return null;
  return (
    <section className="grid gap-3">
      <div>
        <h2 className="text-xl font-semibold m-0">What does the company say about its future?</h2>
        <p className="mute text-sm m-0 mt-1">Quoted word for word from its annual report filed {longDate(p.source.filed)}. <a href={p.source.url} target="_blank" rel="noreferrer" className="underline">Read the filing</a></p>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {groups.filter(([, s]) => s.length).map(([title, items]) => (
          <div key={title} className="card p-5 grid gap-3 content-start">
            <span className="font-semibold text-sm">{title}</span>
            {items.map((t) => <blockquote key={t} className="m-0 pl-3 text-sm leading-relaxed" style={{ borderLeft: "3px solid var(--blue)" }}>{t}</blockquote>)}
          </div>
        ))}
      </div>
    </section>
  );
}

function MarketBlock({ m }: { m: NonNullable<Report["market"]> }) {
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
      <div><h2 className="text-xl font-semibold m-0">What does the market charge for it?</h2><p className="mute text-sm m-0 mt-1">Context for judging the numbers above. It says what investors pay today, not where the price is going.</p></div>
      <div className="card p-5 grid gap-4">
        <div className="flex items-baseline gap-3 flex-wrap">
          <span className="num text-3xl font-semibold">{m.currency === "USD" ? "$" : ""}{m.price.toFixed(2)}</span>
          <span className="mute text-sm">share price on {longDate(m.price_date)}</span>
        </div>
        {pos != null && (
          <div className="max-w-md">
            <div className="relative h-2 rounded-full" style={{ background: "var(--line)" }}><span className="absolute top-1/2 w-3 h-3 rounded-full" style={{ left: `calc(${pos * 100}% - 6px)`, transform: "translateY(-50%)", background: "var(--blue)" }} /></div>
            <div className="flex justify-between text-xs mute num mt-1"><span>52-week low {lo!.toFixed(2)}</span><span>high {hi!.toFixed(2)}</span></div>
          </div>
        )}
        {m.history.length > 2 && <Spark data={m.history.map((h) => h.close)} w={420} h={50} />}
        {rows.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
            {rows.map(([l, v, t]) => (
              <div key={l} className="grid gap-0.5"><span className="text-xs mute">{l}</span><span className="num text-lg font-semibold">{v}</span><span className="mute text-[11px] leading-snug">{t}</span></div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function NewsBlock({ n }: { n: News }) {
  const lines = n.lines, heads = n.articles;
  if (!lines.length && !heads.length) return null;
  return (
    <section className="grid gap-3">
      <div>
        <h2 className="text-xl font-semibold m-0">What has happened lately?</h2>
        <p className="mute text-sm m-0 mt-1 max-w-3xl">From news sites, found on {longDate(n.retrieved)}. Each line is summarised by an AI from one article and checked against that article's own numbers. Open the link before relying on it: news is not part of the financial figures on this page.</p>
      </div>
      <div className="card p-5 grid gap-3">
        {lines.length > 0
          ? lines.map((l) => (
              <div key={l.url} className="grid gap-0.5">
                <p className="m-0 text-sm leading-relaxed">{l.text}</p>
                <a href={l.url} target="_blank" rel="noreferrer" className="text-xs underline" style={{ color: "var(--blue)" }}>{l.source}{l.age ? `, ${l.age}` : ""}: {l.title}</a>
              </div>
            ))
          : heads.map((a) => (
              <a key={a.url} href={a.url} target="_blank" rel="noreferrer" className="text-sm underline" style={{ color: "var(--blue)" }}>{a.source}{a.age ? `, ${a.age}` : ""}: {a.title}</a>
            ))}
      </div>
    </section>
  );
}
