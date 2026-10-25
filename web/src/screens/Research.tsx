import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarsLoader, ErrorBox, Skeleton } from "../components/bits";
import { demoMode, researchHref, type ResearchView } from "../route";
import { CompanySearch } from "../components/CompanySearch";
import { PanelRoster } from "../components/PanelRoster";
import { ShowcaseVideo } from "../components/Showcase";
import { ResearchingRoom } from "../components/ResearchingRoom";
import { recallPicked } from "../recent";
import { RESEARCH_STEPS, STEP_SECONDS, type Report } from "../research";
import { DataSource } from "./ResearchParts";
import { FinancialsTab, InvestorsTab, OverviewTab, SourcesTab, ValueTab } from "./ResearchTabs";
import { Guide, Say } from "../components/Say";

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
  ["Lets you question the investors", "The investors give their calls, face off, and answer your why."],
] as const;
/* Figures from README "Results" and research/evidence.json (the 2018-2023 back-test), not computed here. */
const PROOF = [
  ["50", "companies replayed, 2018 to 2024", "Every call made with only the filings public that day, then graded against the next ones."],
  ["322", "lessons from the analysts' own misses", "Each wrong call from 2018 to 2022 became a lesson the same analyst reads next time."],
  ["13% vs 2%", "dividend cuts or auditor changes", "Companies failing most of Munger's checks against those passing most, over 1,184 company-quarters."],
] as const;

function Landing() {
  const [q, setQ] = useState("");

  return (
    <div className="grid gap-12">
      <section className="card overflow-hidden grid gap-8 lg:gap-10 p-6 md:p-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] items-center"
        style={{ background: "linear-gradient(135deg, color-mix(in srgb, var(--accent) 8%, var(--card)), var(--card) 60%)" }}>
        <div className="grid gap-5 content-center">
          <span className="chip justify-self-start">Research from SEC filings</span>
          <div className="grid gap-3">
            <h1 className="text-3xl md:text-4xl lg:text-5xl font-semibold m-0">Is this company worth your money? Check the filings.</h1>
            <p className="m-0 text-base md:text-lg leading-relaxed mute max-w-xl">Type a company name or ticker. Five investors read its SEC filings and show what a careful investor would look at, with every number traced to its source.</p>
          </div>

          <CompanySearch q={q} onQ={setQ} autoFocus />

          <div className="flex items-center gap-2 flex-wrap text-sm">
            <span className="mute">Try</span>
            {EXAMPLES.map((e) => <button key={e} className="chip cursor-pointer bg-transparent" onClick={() => setQ(e)}>{e}</button>)}
          </div>
          <Guide title="New to this?">Type the name of any company listed in the US. We read the reports it must publish for investors (called filings) and show the key figures in plain terms, then five famous investing styles give their view. It is a way to learn about a company, not advice on what to buy.</Guide>
          <p className="mute text-xs m-0">Covers companies listed in the United States (NYSE and Nasdaq). London and European listings are coming.</p>
        </div>

        <ShowcaseVideo />
      </section>

      <section aria-label="Evidence" className="grid gap-4">
        <div className="max-w-2xl grid gap-1">
          <h2 className="text-xl md:text-2xl font-semibold m-0">Checked against what really happened</h2>
          <p className="m-0 mute text-sm leading-relaxed">We grade our own analysts and publish the result, including the parts that are not flattering.</p>
        </div>
        <ul className="m-0 p-0 list-none grid gap-3 md:grid-cols-3">
          {PROOF.map(([n, h, t]) => (
            <li key={h} className="card p-5 grid gap-1 content-start">
              <span className="num text-3xl md:text-4xl font-semibold leading-none" style={{ color: "var(--accent)", fontFamily: "var(--font-display)" }}>{n}</span>
              <span className="text-sm font-semibold mt-2">{h}</span>
              <span className="mute text-sm leading-relaxed">{t}</span>
            </li>
          ))}
        </ul>
        <p className="text-sm mute m-0 max-w-3xl">The analysts that learn from their misses did not beat an identical copy that never learns on the unseen 2023-24 years. <a href="#/mubit" className="underline underline-offset-4">See the full track record</a>.</p>
      </section>

      <PanelRoster />

      <section aria-label="How it works" className="grid gap-5">
        <h2 className="text-xl md:text-2xl font-semibold m-0">How it works</h2>
        <ol className="m-0 p-0 list-none grid gap-x-6 gap-y-5 sm:grid-cols-2 lg:grid-cols-4">
          {HOW.map(([h, t], i) => (
            <li key={h} className="grid gap-2 content-start">
              <span className="num inline-grid place-items-center w-7 h-7 rounded-full text-sm font-semibold" style={{ background: "var(--accent)", color: "#1a1006" }}>{i + 1}</span>
              <span className="text-sm font-semibold">{h}</span>
              <span className="mute text-sm leading-relaxed"><Say>{t}</Say></span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

/* ───────────────────────── the company pages ───────────────────────── */

function Loading({ name }: { name?: string }) {
  const [i, setI] = useState(0);
  useEffect(() => { const t = setInterval(() => setI((x) => Math.min(x + 1, RESEARCH_STEPS.length - 1)), STEP_SECONDS * 1000); return () => clearInterval(t); }, []);
  return (
    <div className="card p-8 grid gap-4" role="status">
      <div className="flex items-center gap-4"><BarsLoader /><h1 className="text-2xl font-bold m-0">Researching {name ?? "the company"}…</h1></div>
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
  { id: "investors", label: "Investor panel", hint: "The investors give their calls, face off, and you can question each one" },
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
    <nav ref={row} aria-label="Pages of this report" className="tabrow sticky top-0 sm:top-12 z-[var(--z-sticky)] flex" style={{ background: "var(--background)", borderBottom: "1px solid var(--divider)" }}>
      {TABS.map((t) => (
        <a key={t.id} href={researchHref(cik, t.id)} title={t.hint} aria-current={view === t.id ? "page" : undefined}
          className="tab px-4 py-3 text-sm font-medium no-underline whitespace-nowrap">{t.label}</a>
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
  if (q.isError || !q.data) return <div className="grid gap-3"><ErrorBox msg={q.error instanceof Error ? q.error.message : "Could not build the report."} onRetry={() => q.refetch()} /><a className="btn ghost justify-self-start no-underline" href="#/">← Search again</a></div>;
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
    <div className="grid gap-4 grid-cols-[minmax(0,1fr)]">
      <header className="grid gap-1">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-baseline gap-x-3 gap-y-1 flex-wrap">
            <h1 className="text-2xl font-semibold m-0">{c.ticker || c.name}</h1>
            <span className="text-base">{c.ticker ? c.name : ""}</span>
            <span className="mute text-xs">{c.exchange} · United States</span>
          </div>
          <div className="flex gap-2 flex-wrap">
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
