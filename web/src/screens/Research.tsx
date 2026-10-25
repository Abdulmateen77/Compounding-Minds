import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ErrorBox, Skeleton } from "../components/bits";
import { demoMode, researchHref, type ResearchView } from "../route";
import { CompanySearch, SearchOptions } from "../components/CompanySearch";
import { ResearchingRoom } from "../components/ResearchingRoom";
import { recallPicked } from "../recent";
import { RESEARCH_STEPS, STEP_SECONDS, type Report } from "../research";
import { DataSource } from "./ResearchParts";
import { FinancialsTab, InvestorsTab, OverviewTab, SourcesTab, ValueTab } from "./ResearchTabs";

const j = async <T,>(url: string): Promise<T> => {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText);
  return r.json();
};

export default function Research({ cik, view = "overview" }: { cik?: string; view?: ResearchView }) {
  return cik ? <ReportPage cik={cik} view={view} /> : <Landing />;
}

/* ───────────────────────── landing: one question, one box ───────────────────────── */

const EXAMPLES = ["Tesla", "Apple", "Coca-Cola", "Nvidia", "Walmart"];
const HOW = [
  ["Reads the filings", "Every figure comes from the company's own SEC reports, worked out by code, not guessed by an AI."],
  ["Asks the investor's questions", "Is it growing? Does profit turn into cash? Is the balance sheet safe?"],
  ["Shows its working", "Each number names its filing; the company's own words are quoted with a link."],
  ["Lets you question the investors", "Six investors give their calls, face off, and answer your why."],
] as const;

function Landing() {
  const [q, setQ] = useState("");

  return (
    <div className="grid gap-8">
      <section className="card p-6 md:p-10 grid gap-6" style={{ background: "linear-gradient(135deg, color-mix(in srgb, var(--primary) 10%, var(--card)), var(--card))" }}>
        <div className="max-w-2xl grid gap-3">
          <h1 className="text-3xl md:text-5xl font-bold m-0">Is this company worth your money? Check the filings.</h1>
          <p className="m-0 text-base md:text-lg leading-relaxed mute">Type a company name or ticker. We read its SEC filings and show what a careful investor would look at.</p>
        </div>

        <CompanySearch q={q} onQ={setQ} autoFocus />

        <div className="flex items-center gap-2 flex-wrap text-sm">
          <span className="mute">Try</span>
          {EXAMPLES.map((e) => <button key={e} className="chip cursor-pointer bg-transparent" onClick={() => setQ(e)}>{e}</button>)}
        </div>
        <SearchOptions />
        <p className="mute text-xs m-0">Covers companies listed in the United States (NYSE and Nasdaq). London and European listings are coming.</p>
      </section>

      <section aria-label="How it works" className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
        {HOW.map(([h, t], i) => (
          <div key={h} className="grid gap-1 content-start">
            <span className="text-sm font-semibold"><span className="num mute">{i + 1}</span>  {h}</span>
            <span className="mute text-sm leading-relaxed">{t}</span>
          </div>
        ))}
      </section>

      <p className="text-sm mute m-0">How accurate have the checks been? See the <a href="#/mubit" className="underline underline-offset-4">track record</a>.</p>
    </div>
  );
}

/* ───────────────────────── the company pages ───────────────────────── */

function Loading({ name }: { name?: string }) {
  const [i, setI] = useState(0);
  useEffect(() => { const t = setInterval(() => setI((x) => Math.min(x + 1, RESEARCH_STEPS.length - 1)), STEP_SECONDS * 1000); return () => clearInterval(t); }, []);
  return (
    <div className="card p-8 grid gap-4" role="status">
      <h1 className="text-2xl font-bold m-0">Researching {name ?? "the company"}…</h1>
      <ol className="m-0 p-0 list-none grid gap-2 text-sm">
        {RESEARCH_STEPS.map((s, k) => (
          <li key={s} className="flex items-center gap-3" style={{ opacity: k <= i ? 1 : 0.35 }}>
            <span aria-hidden className="inline-grid place-items-center w-5 h-5 rounded-full text-xs" style={{ background: k < i ? "var(--success)" : "var(--card-alt)", color: k < i ? "var(--on-success)" : "var(--muted)" }}>{k < i ? "✓" : k === i ? "…" : ""}</span>
            {s}
          </li>
        ))}
      </ol>
      <p className="mute text-sm m-0">The first lookup takes 20 to 30 seconds: it reads the filings, the annual report and the latest news. Later ones are instant.</p>
      <Skeleton h={80} />
    </div>
  );
}

const TABS: { id: ResearchView; label: string; hint: string }[] = [
  { id: "overview", label: "Overview", hint: "The short answer: is it any good, and what stands out" },
  { id: "financials", label: "Financials", hint: "Growth, profit, cash, debt and risk, one question at a time" },
  { id: "value", label: "Value and outlook", hint: "What the market charges, what it could be worth, and the next five years" },
  { id: "investors", label: "Investor panel", hint: "Six investors give their calls, face off, and you can question each one" },
  { id: "sources", label: "Sources and data", hint: "Every figure, check and filing as tables, with a CSV export" },
];

/** The page tabs. Sticky, scrolls sideways on a phone, and keeps the current tab in view when the page changes. */
function TabBar({ cik, view }: { cik: string; view: ResearchView }) {
  const row = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const on = row.current?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!on || !row.current) return;
    const box = row.current, left = on.offsetLeft - (box.clientWidth - on.clientWidth) / 2;
    box.scrollTo({ left: Math.max(0, left), behavior: "smooth" });   // scrolls the row itself, never the page
  }, [view]);
  return (
    <nav ref={row} aria-label="Pages of this report" className="tabrow sticky top-0 z-[var(--z-sticky)] -mx-4 sm:-mx-6 px-4 sm:px-6 py-2 flex gap-1" style={{ background: "color-mix(in srgb, var(--background) 88%, transparent)", backdropFilter: "blur(8px)", borderBottom: "1px solid var(--divider)" }}>
      {TABS.map((t) => (
        <a key={t.id} href={researchHref(cik, t.id)} title={t.hint} aria-current={view === t.id ? "page" : undefined}
          className="px-4 py-2 rounded-lg text-sm font-medium no-underline whitespace-nowrap"
          style={view === t.id ? { background: "var(--card)", color: "var(--foreground)", boxShadow: "0 0 0 1px var(--divider)" } : { color: "var(--muted)" }}>{t.label}</a>
      ))}
    </nav>
  );
}

function ReportPage({ cik, view: asked }: { cik: string; view: ResearchView }) {
  // ?demo=1 (presenter mode) always means the investor panel, wherever the link points.
  const view: ResearchView = asked === "overview" && demoMode() ? "investors" : asked;
  const [copied, setCopied] = useState(false);
  const q = useQuery({ queryKey: ["report", cik], queryFn: () => j<Report>(`/api/research/company/${cik}`), staleTime: 10 * 60_000, retry: 0 });
  const waited = useRef(false);               // the investors were shown researching, so the readings continue from there
  if (q.isLoading) {
    if (view === "investors") { waited.current = true; return <ResearchingRoom cik={cik} plain={(name) => <Loading name={name} />} />; }
    return <Loading name={recallPicked(cik)?.name} />;
  }
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

  return (
    <div className="grid gap-6 grid-cols-[minmax(0,1fr)]">
      <header className="grid gap-2">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <h1 className="text-3xl md:text-4xl font-bold m-0">{c.name}</h1>
            <p className="mute m-0 mt-1 text-sm"><span className="num">{c.ticker}</span> · {c.exchange} · United States</p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <a className="btn ghost sm no-underline" href="#/">← Search again</a>
            <button className="btn ghost sm" onClick={() => { navigator.clipboard?.writeText(window.location.href).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); }); }}>{copied ? "Link copied" : "Copy link"}</button>
            <button className="btn ghost sm" onClick={() => { fetch(`/api/research/company/${cik}?refresh=true`).then(() => q.refetch()); }}>Refresh data</button>
          </div>
        </div>
        <DataSource r={r} />
      </header>

      <TabBar cik={cik} view={view} />

      {view === "overview" && <OverviewTab r={r} />}
      {view === "financials" && <FinancialsTab r={r} />}
      {view === "value" && <ValueTab r={r} />}
      {view === "investors" && <InvestorsTab r={r} fromLoading={waited.current} />}
      {view === "sources" && <SourcesTab r={r} />}
    </div>
  );
}
