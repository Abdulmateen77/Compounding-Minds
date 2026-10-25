import { useCallback, useRef, useState } from "react";
import type { ChatMsg } from "../chat";
import { FadeIn } from "../components/FadeIn";
import { Disclosure, Head } from "../components/Section";
import { AnalysisPopup } from "../components/AnalysisPopup";
import type { Speech } from "../components/DebateLog";
import { DebateSection } from "../components/DebateSection";
import { InvestorStage } from "../components/InvestorStage";
import { InvestorBoard } from "../components/InvestorBoard";
import { PanelDeck } from "../components/PanelDeck";
import { OutlookBlock } from "../components/Outlook";
import { PanelVerdict } from "../components/PanelParts";
import { researchHref } from "../route";
import { fmtValue, type Report } from "../research";
import { EvidenceLink } from "./EvidenceLink";
import { Future, QuickCheckBlock, Worth } from "./ResearchAnalysis";
import ProView from "./ResearchPro";
import { DataSource, FinSection, Highlights, MarketBlock, NewsBlock, Plans, RiskChecks, Summary, TrendChart } from "./ResearchParts";
import { Guide, Say } from "../components/Say";
import { useEffectiveLevel } from "../literacy";

/* One component per company page. Each answers one question and shows each thing once; the tab bar in Research.tsx moves between them. */

/** Is it any good? The verdict, the headline figures, what stands out, the quick screen, then the investors and their calls (each
    opens their analysis, or a chat with them), and the latest news. */
export function OverviewTab({ r }: { r: Report }) {
  const a = r.analysis;
  const [open, setOpen] = useState<{ i: number; on: "analysis" | "ask" } | null>(null);
  const [chats, setChats] = useState<Record<string, ChatMsg[]>>({});
  const lens = open && a ? a.lenses[open.i] : undefined;
  return (
    <div className="grid gap-8 grid-cols-[minmax(0,1fr)]">
      <Guide title="How to read this page">This is the short answer. The top box is what five famous investing styles make of the company. The tiles are its key figures, and the lists show what stands out, good and bad. The colours describe what the filings show; they are not a tip to buy or sell.</Guide>
      {a && <PanelVerdict a={a} name={r.company.name} title="The investors' take on" />}
      <Summary r={r} />
      <FadeIn><Highlights r={r} /></FadeIn>
      {r.quick_check && <FadeIn><QuickCheckBlock q={r.quick_check} /></FadeIn>}
      {a && a.lenses.length > 0 && <InvestorBoard lenses={a.lenses} onAnalysis={(i) => setOpen({ i, on: "analysis" })} onAsk={(i) => setOpen({ i, on: "ask" })} />}
      {r.news && <FadeIn><NewsBlock n={r.news} /></FadeIn>}
      {lens && open && (
        <AnalysisPopup key={`${lens.key}-${open.on}`} l={lens} startOn={open.on} onClose={() => setOpen(null)}
          ask={{ cik: r.company.cik, messages: chats[lens.key] ?? [], setMessages: (f) => setChats((c) => ({ ...c, [lens.key]: f(c[lens.key] ?? []) })) }} />
      )}
    </div>
  );
}

/** How are the numbers? Six years in one chart, then growth, profit, cash, balance sheet and reinvestment, then the risk checks. */
export function FinancialsTab({ r }: { r: Report }) {
  const sections = r.sections!, byId = (id: string) => sections.find((s) => s.id === id)!;
  const [mode, setMode] = useState<{ open: boolean; n: number }>({ open: false, n: 0 });   // n re-keys the sections so "Expand all" takes effect
  return (
    <div className="grid gap-6 grid-cols-[minmax(0,1fr)]">
      <Guide title="How to read this page">Sales are the money a company takes in. Profit is what is left after its costs. Cash is what actually arrives in the bank, and it can differ from profit. Debt is money it has to pay back. Each section below asks one of those questions; open one to see the figures.</Guide>
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
      <Guide title="How to read this page">Price is what the stock market charges for the company today. Value is what the business itself might be worth from the cash it earns. The two can stay apart for years. The cases below show what would have to be true for the price to make sense.</Guide>
      {r.market && <MarketBlock m={r.market} />}
      {r.analysis && <FadeIn><Worth a={r.analysis} /></FadeIn>}
      {r.outlook
        ? <OutlookBlock o={r.outlook} market={r.market}>
            {r.analysis?.future && (
              <Disclosure level={3} title="Ten-year scenario table" summary="Sales and free cash flow after 1, 3, 5 and 10 years under each case">
                <Future a={r.analysis} bare />
              </Disclosure>
            )}
          </OutlookBlock>
        : r.analysis?.future && <Future a={r.analysis} />}
      {r.plans && <FadeIn><Plans p={r.plans} /></FadeIn>}
    </div>
  );
}

/** What do the investors make of it? The 3D office first: the investors at their desks, working through their checks and arguing it
    out. Then the answer, the investors and their calls, a box to question any of them, and the written debate. Everything is open at
    once. The proof that the checks work lives on the Track record page. */
export function InvestorsTab({ r, fromLoading }: { r: Report; fromLoading: boolean }) {
  const a = r.analysis;
  const [popup, setPopup] = useState<number | null>(null);
  const [chats, setChats] = useState<Record<string, ChatMsg[]>>({});
  const [speech, setSpeech] = useState<Speech | null>(null);        // who the written debate is on, so the office says the same line
  const stage = useRef<HTMLDivElement | null>(null), speaking = useRef(false);
  const onSpeak = useCallback((s: Speech | null) => {
    if (s && !speaking.current) stage.current?.scrollIntoView({ behavior: "smooth", block: "start" });   // bring the office into sight as the debate starts
    speaking.current = !!s;
    setSpeech(s);
  }, []);
  if (!a || a.lenses.length === 0) return <p className="card p-5 m-0 text-sm">There is not enough in the filings for the investors to give a view.</p>;

  return (
    <div className="grid gap-6 grid-cols-[minmax(0,1fr)]">
      <Guide title="How to read this page">Five well-known investors, each with their own habits of thought, are applied to this company as a list of rule checks. They often disagree, and that is the point. Press play to watch them argue, or ask any of them why they reached their call.</Guide>
      <section ref={stage} className="grid gap-3 grid-cols-[minmax(0,1fr)]" aria-label="The investors at work" style={{ scrollMarginTop: 72 }}>
        <Head title="The investor panel at work" blurb="Watch the five investors work through their checks, give their readings and argue where they disagree. Click an investor, here or in the office, for their analysis." />
        <InvestorStage r={r} fromLoading={fromLoading} speech={speech} onPick={setPopup} />
      </section>
      <PanelDeck lenses={a.lenses} speaking={speech?.who ?? null} onOpen={setPopup} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem] items-start">
        <FadeIn><DebateSection r={r} onSpeak={onSpeak} /></FadeIn>
        <FadeIn><PanelVerdict a={a} name={r.company.name} title="The panel's view on" compact /></FadeIn>
      </div>
      <FadeIn><EvidenceLink /></FadeIn>
      {popup != null && a.lenses[popup] && (
        <AnalysisPopup key={a.lenses[popup].key} l={a.lenses[popup]} onClose={() => setPopup(null)}
          ask={{ cik: r.company.cik, messages: chats[a.lenses[popup].key] ?? [], setMessages: (f) => setChats((c) => ({ ...c, [a.lenses[popup].key]: f(c[a.lenses[popup].key] ?? []) })) }} />
      )}
    </div>
  );
}

/** Where does it all come from? The data source, every table, the economy and the notes. Reference, not reading. */
export function SourcesTab({ r }: { r: Report }) {
  const econ = r.economy ?? [];
  const level = useEffectiveLevel();
  return (
    <div className="grid gap-6 grid-cols-[minmax(0,1fr)]">
      <Guide title="How to read this page">This is the reference page. Every figure comes from a report the company had to file with the US regulator (the SEC). The tables at the bottom can be downloaded if you want to check anything yourself.</Guide>
      <Head title="Where the numbers come from" blurb="Computed in Python from filings the company made to the SEC. No figure on these pages is written by an AI." />
      <DataSource r={r} full />
      {econ.length > 0 && (
        <Disclosure title="What is the economy doing?" count={`${econ.length} indicators`} summary="Context for how this company's sales might move, as reported to date.">
          <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
            {econ.map((e) => (
              <div key={e.key} className="rounded-xl p-4 grid gap-1" style={{ background: "var(--card-alt)" }}>
                <div className="flex items-baseline justify-between gap-2"><span className="text-sm font-medium"><Say>{e.label}</Say></span><span className="num text-lg font-semibold">{fmtValue(e.unit, e.value)}</span></div>
                {level !== "advanced" && <span className="mute text-xs"><Say>{e.meaning}</Say></span>}
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
