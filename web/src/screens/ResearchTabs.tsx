import { useState } from "react";
import type { ChatMsg } from "../chat";
import { Disclosure, Head } from "../components/Section";
import { AnalysisPopup } from "../components/AnalysisPopup";
import { AskInvestor } from "../components/AskInvestor";
import { DebateSection } from "../components/DebateSection";
import { InvestorBoard } from "../components/InvestorBoard";
import { OutlookBlock } from "../components/Outlook";
import { PanelVerdict } from "../components/PanelParts";
import { researchHref } from "../route";
import { fmtValue, type Report } from "../research";
import { EvidenceLink } from "./EvidenceLink";
import { Future, QuickCheckBlock, Worth } from "./ResearchAnalysis";
import ProView from "./ResearchPro";
import { DataSource, FinSection, Highlights, MarketBlock, NewsBlock, Plans, RiskChecks, Summary, TrendChart } from "./ResearchParts";

/* One component per company page. Each answers one question and shows each thing once; the tab bar in Research.tsx moves between them. */

/** Is it any good? The verdict, the headline figures, what stands out, the quick screen and the latest news. */
export function OverviewTab({ r }: { r: Report }) {
  return (
    <div className="grid gap-8 grid-cols-[minmax(0,1fr)]">
      {r.analysis && <PanelVerdict a={r.analysis} name={r.company.name} title="The investors' take on" />}
      <Summary r={r} />
      <Highlights r={r} />
      {r.quick_check && <QuickCheckBlock q={r.quick_check} />}
      {r.news && <NewsBlock n={r.news} />}
    </div>
  );
}

/** How are the numbers? Six years in one chart, then growth, profit, cash, balance sheet and reinvestment, then the risk checks. */
export function FinancialsTab({ r }: { r: Report }) {
  const sections = r.sections!, byId = (id: string) => sections.find((s) => s.id === id)!;
  const [mode, setMode] = useState<{ open: boolean; n: number }>({ open: false, n: 0 });   // n re-keys the sections so "Expand all" takes effect
  return (
    <div className="grid gap-6 grid-cols-[minmax(0,1fr)]">
      <TrendChart sections={sections} />
      <div className="grid gap-3">
        <Head title="The numbers, one question at a time" blurb="Each line shows its leading figures; open it for the reading and every figure."
          right={<button className="btn ghost" onClick={() => setMode((m) => ({ open: !m.open, n: m.n + 1 }))}>{mode.open ? "Collapse all" : "Expand all"}</button>} />
        {(["growth", "profit", "cash", "balance", "reinvest"] as const).map((id) => (
          <FinSection key={`${id}-${mode.n}`} s={byId(id)} through={r.data_through!} defaultOpen={mode.open} />
        ))}
        <RiskChecks key={`risk-${mode.n}`} flags={r.risk_flags ?? []} />
      </div>
    </div>
  );
}

/** What is it worth and where is it heading? The price, a cash-flow valuation, the next five years, and what management says. */
export function ValueTab({ r }: { r: Report }) {
  return (
    <div className="grid gap-8 grid-cols-[minmax(0,1fr)]">
      {r.market && <MarketBlock m={r.market} />}
      {r.analysis && <Worth a={r.analysis} />}
      {r.outlook
        ? <OutlookBlock o={r.outlook} market={r.market}>
            {r.analysis?.future && (
              <Disclosure level={3} title="Ten-year scenario table" summary="Sales and free cash flow after 1, 3, 5 and 10 years under each case">
                <Future a={r.analysis} bare />
              </Disclosure>
            )}
          </OutlookBlock>
        : r.analysis?.future && <Future a={r.analysis} />}
      {r.plans && <Plans p={r.plans} />}
    </div>
  );
}

/** What do the investors make of it? The answer, then the investors and their calls, then a box to question any of them, then the
    debate. Everything here is open at once; the 3D debate is an optional extra inside the last part. The proof that the checks work
    lives on the Track record page. */
export function InvestorsTab({ r, fromLoading }: { r: Report; fromLoading: boolean }) {
  const a = r.analysis;
  const [sel, setSel] = useState<number | null>(0);                 // who the ask box is talking to (the first investor until you choose)
  const [chosen, setChosen] = useState(false);                      // you chose someone: only then does the cursor jump into the box
  const [popup, setPopup] = useState<number | null>(null);
  const [chats, setChats] = useState<Record<string, ChatMsg[]>>({});
  if (!a || a.lenses.length === 0) return <p className="card p-5 m-0 text-sm">There is not enough in the filings for the investors to give a view.</p>;

  const ask = (i: number) => {
    setPopup(null); setSel(i); setChosen(true);
    window.setTimeout(() => document.getElementById("ask")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  };
  return (
    <div className="grid gap-8 grid-cols-[minmax(0,1fr)]">
      <PanelVerdict a={a} name={r.company.name} title="The panel's view on" />
      <InvestorBoard lenses={a.lenses} onAnalysis={setPopup} onAsk={ask} />
      <AskInvestor cik={r.company.cik} lenses={a.lenses} sel={sel} setSel={(i) => { setSel(i); setChosen(i != null); }} chats={chats} setChats={setChats} focus={chosen} />
      <DebateSection r={r} fromLoading={fromLoading} onPick={setPopup} />
      <EvidenceLink />
      {popup != null && a.lenses[popup] && <AnalysisPopup l={a.lenses[popup]} onClose={() => setPopup(null)} onAsk={() => ask(popup)} />}
    </div>
  );
}

/** Where does it all come from? The data source, every table, the economy and the notes. Reference, not reading. */
export function SourcesTab({ r }: { r: Report }) {
  const econ = r.economy ?? [];
  return (
    <div className="grid gap-6 grid-cols-[minmax(0,1fr)]">
      <Head title="Where the numbers come from" blurb="Computed in Python from filings the company made to the SEC. No figure on these pages is written by an AI." />
      <DataSource r={r} full />
      {econ.length > 0 && (
        <Disclosure title="What is the economy doing?" count={`${econ.length} indicators`} summary="Context for how this company's sales might move, as reported to date.">
          <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
            {econ.map((e) => (
              <div key={e.key} className="rounded-xl p-4 grid gap-1" style={{ background: "var(--card-alt)" }}>
                <div className="flex items-baseline justify-between gap-2"><span className="text-sm font-medium">{e.label}</span><span className="num text-lg font-semibold">{fmtValue(e.unit, e.value)}</span></div>
                <span className="mute text-xs">{e.meaning}</span>
              </div>
            ))}
          </div>
        </Disclosure>
      )}
      <ProView r={r} />
      <div className="grid gap-2 text-xs mute">
        {(r.notes ?? []).map((n) => <p key={n} className="m-0">Note: {n}</p>)}
        {(r.missing ?? []).length > 0 && <p className="m-0">Not reported in its filings: {r.missing!.join(", ")}.</p>}
        <p className="m-0">See all of its filings <a href={r.sec_url} target="_blank" rel="noreferrer" className="underline">on EDGAR</a>. Good, watch and concern labels are rules of thumb that describe the evidence; they are not advice.</p>
        <p className="m-0"><a href={researchHref(r.company.cik, "overview")} className="underline">Back to the overview</a></p>
      </div>
    </div>
  );
}
