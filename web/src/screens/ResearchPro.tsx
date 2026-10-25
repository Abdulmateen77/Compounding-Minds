import { useMemo, useState } from "react";
import { Disclosure } from "../components/Section";
import { TONE, fmtValue, longDate, money, multiple, pctOf, type Check, type Figure, type Report } from "../research";

/* The professional view: the same computed numbers as the written report, as tables. No narrative, no AI text. Every row is
   a figure or a check from research/report.py and research/analysis.py, with the filings it came from. */

const RESULT = {
  pass: { tag: "PASS", color: "var(--green)" },
  partial: { tag: "PART", color: "var(--amber)" },
  fail: { tag: "FAIL", color: "var(--red)" },
  unknown: { tag: "N/A", color: "var(--mute)" },
} as const;
type Result = keyof typeof RESULT;
const RESULTS = Object.keys(RESULT) as Result[];

const OVERALL: Record<string, string> = { look: "Worth a look", wait: "Wait for price", avoid: "Avoid for now", weak: "Weak quality", mixed: "Mixed evidence" };
const fit = (v: number | null) => (v == null ? "n/a" : `${Math.round(v * 100)}%`);
const edgar = (cik: number, acc: string) => `https://www.sec.gov/Archives/edgar/data/${cik}/${acc.replace(/-/g, "")}/`;
const csvCell = (s: string) => `"${s.replace(/"/g, '""')}"`;

function Th({ children, right }: { children?: React.ReactNode; right?: boolean }) {
  return <th className="text-left font-semibold py-2 px-3 whitespace-nowrap mute text-[11px] uppercase tracking-wide" style={{ textAlign: right ? "right" : "left", borderBottom: "1px solid var(--line)" }}>{children}</th>;
}
const td = "py-1.5 px-3 align-top";
const rowLine = { borderBottom: "1px solid color-mix(in srgb, var(--line) 55%, transparent)" } as const;

function Block({ title, note, right, open = false, children }: { title: string; note?: string; right?: React.ReactNode; open?: boolean; children: React.ReactNode }) {
  return (
    <Disclosure level={3} title={title} summary={note} defaultOpen={open}>
      {note && <p className="mute text-xs m-0 max-w-3xl">{note}</p>}
      {right && <div className="flex justify-end">{right}</div>}
      <div className="overflow-x-auto rounded-xl" style={{ border: "1px solid var(--line)" }}>{children}</div>
    </Disclosure>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return <div className="card px-3 py-2 grid gap-0.5"><span className="mute text-[11px] uppercase tracking-wide">{k}</span><span className="num text-base font-semibold">{v}</span></div>;
}

export default function ProView({ r }: { r: Report }) {
  const a = r.analysis, m = r.market, v = a?.valuation, cik = r.company.cik;
  const [only, setOnly] = useState<Result | "all">("all");
  const [who, setWho] = useState<string>("all");

  const rows = useMemo(() => (a?.lenses ?? []).flatMap((l) => l.checks.map((k) => ({ lens: l, k }))), [a]);
  const shown = rows.filter(({ lens, k }) => (who === "all" || lens.key === who) && (only === "all" || k.result === only));
  const figures = (r.sections ?? []).flatMap((s) => s.figures.map((f) => ({ s, f })));
  const accessions = useMemo(() => {
    const seen = new Set<string>();
    for (const { f } of figures) f.sources.forEach((x) => seen.add(x));
    (r.risk_flags ?? []).forEach((fl) => fl.sources.forEach((x) => seen.add(x)));
    return [...seen].sort().reverse();
  }, [r]);   // eslint-disable-line react-hooks/exhaustive-deps

  const exportCsv = () => {
    const head = ["investor", "check_id", "check", "result", "found", "idea", "source"];
    const lines = [head.join(","), ...rows.map(({ lens, k }) => [lens.name, k.id, k.check, k.result, k.shown, k.principle, k.source].map(csvCell).join(","))];
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    const el = document.createElement("a");
    el.href = url; el.download = `${r.company.ticker ?? r.company.cik}-investor-checks.csv`; el.click();
    URL.revokeObjectURL(url);
  };

  const hist = (f: Figure) => f.history.slice(-5).map((h) => (h.value == null ? "–" : fmtValue(f.unit, h.value))).join("  →  ");

  return (
    <div className="grid gap-3">
      <p className="mute text-xs m-0">Every table below is computed from SEC filings through {r.data_through ? longDate(r.data_through) : "n/a"} and names its source. Open one to read it.</p>

      {m && (
        <Block title="Market snapshot" note={`Price, value and yield measures on ${m.price_date}.`}>
          <div className="grid gap-2 grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 p-3">
            <Stat k={`Price (${m.price_date})`} v={`${m.currency} ${m.price.toFixed(2)}`} />
            <Stat k="Market cap" v={m.market_cap ? money(m.market_cap) : "n/a"} />
            <Stat k="Enterprise value" v={m.enterprise_value ? money(m.enterprise_value) : "n/a"} />
            <Stat k="P/E (TTM)" v={multiple(m.pe)} />
            <Stat k="EV/EBITDA" v={multiple(m.ev_to_ebitda)} />
            <Stat k="Price/sales" v={multiple(m.price_to_sales)} />
            <Stat k="FCF yield" v={pctOf(m.fcf_yield)} />
            <Stat k="Dividend yield" v={pctOf(m.dividend_yield)} />
            <Stat k="52-week range" v={m.low_52w != null && m.high_52w != null ? `${m.low_52w.toFixed(2)} – ${m.high_52w.toFixed(2)}` : "n/a"} />
            <Stat k="Shares out" v={m.shares ? `${(m.shares / 1e9).toFixed(2)}B` : "n/a"} />
            {a && <Stat k="Overall reading" v={OVERALL[a.overall.key] ?? a.overall.key} />}
            {a && <Stat k="Checks passed" v={(() => { const all = rows.filter(({ k }) => k.result !== "unknown"); return `${all.filter(({ k }) => k.result === "pass").length}/${all.length}`; })()} />}
          </div>
        </Block>
      )}

      {v?.available && v.scenarios && (
        <Block title="Reverse and forward DCF" note={`Owner-earnings DCF on normalised free cash flow ${money(v.normalised_fcf ?? 0)}, ${pctOf(v.discount_rate)} discount rate, ${pctOf(v.long_run_growth)} long-run growth, ${v.years}-year explicit period. Assumptions are inputs, not forecasts.`}>
          <table className="w-full text-xs border-collapse">
            <thead><tr><Th>Case</Th><Th right>Start growth</Th><Th right>Value / share</Th><Th right>Price vs value</Th></tr></thead>
            <tbody>
              {v.scenarios.map((s) => (
                <tr key={s.name} style={rowLine}>
                  <td className={td}>{s.name}</td>
                  <td className={`${td} num text-right`}>{pctOf(s.start_growth)}</td>
                  <td className={`${td} num text-right`}>{s.value_per_share == null ? "n/a" : `$${s.value_per_share.toFixed(2)}`}</td>
                  <td className={`${td} num text-right`}>{s.value_per_share && v.price ? `${((v.price / s.value_per_share - 1) * 100).toFixed(0)}%` : "n/a"}</td>
                </tr>
              ))}
              <tr><td className={td}>Market-implied (reverse DCF)</td><td className={`${td} num text-right`}>{pctOf(v.implied_growth)}</td><td className={`${td} num text-right`}>{v.price ? `$${v.price.toFixed(2)}` : "n/a"}</td><td className={`${td} num text-right`}>—</td></tr>
            </tbody>
          </table>
          {v.sensitivity && v.sensitivity.length > 0 && (
            <table className="w-full text-xs border-collapse" style={{ borderTop: "1px solid var(--line)" }}>
              <thead><tr><Th>Discount rate</Th>{v.scenarios.map((s) => <Th key={s.name} right>{s.name} value / share</Th>)}</tr></thead>
              <tbody>
                {v.sensitivity.map((row) => (
                  <tr key={row.rate} style={rowLine}>
                    <td className={`${td} num`}>{pctOf(row.rate)}</td>
                    {row.values.map((x, i) => <td key={i} className={`${td} num text-right`}>{x == null ? "n/a" : `$${x.toFixed(2)}`}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Block>
      )}

      {a && (
        <Block title="Investor lenses: summary" note="Fit = share of testable checks passed, a partial counting half. Rules, not opinions: the written reading is on the Investor panel page.">
          <table className="w-full text-xs border-collapse">
            <thead><tr><Th>Investor</Th><Th>Reading</Th><Th right>Fit</Th><Th right>Pass</Th><Th right>Part</Th><Th right>Fail</Th><Th right>N/A</Th><Th>Back-tested</Th></tr></thead>
            <tbody>
              {a.lenses.map((l) => {
                const n = (x: Result) => l.checks.filter((k) => k.result === x).length;
                return (
                  <tr key={l.key} style={rowLine}>
                    <td className={`${td} font-medium`}>{l.name}</td><td className={td}>{l.word}</td>
                    <td className={`${td} num text-right`}>{fit(l.fit)}</td>
                    {RESULTS.map((x) => <td key={x} className={`${td} num text-right`} style={{ color: n(x) && x !== "unknown" ? RESULT[x].color : undefined }}>{n(x)}</td>)}
                    <td className={td}>{l.backtested ? "yes" : "no"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Block>
      )}

      {a && (
        <Block title={`All investor checks (${shown.length} of ${rows.length})`}
          right={
            <div className="flex items-center gap-2 flex-wrap text-xs">
              <select aria-label="Investor" value={who} onChange={(e) => setWho(e.target.value)} className="card px-2 py-1" style={{ color: "var(--text)" }}>
                <option value="all">All investors</option>
                {a.lenses.map((l) => <option key={l.key} value={l.key}>{l.name}</option>)}
              </select>
              {(["all", ...RESULTS] as const).map((x) => (
                <button key={x} className="chip cursor-pointer" aria-pressed={only === x} onClick={() => setOnly(x)}
                  style={only === x ? { color: "var(--text)", borderColor: "var(--blue)" } : undefined}>{x === "all" ? "All" : RESULT[x].tag}</button>
              ))}
              <button className="btn ghost" style={{ padding: ".25rem .7rem", fontSize: ".75rem" }} onClick={exportCsv}>Export CSV</button>
            </div>
          }>
          <table className="w-full text-xs border-collapse">
            <thead><tr><Th>Investor</Th><Th>ID</Th><Th>Check</Th><Th>Result</Th><Th>Found</Th><Th>Source</Th></tr></thead>
            <tbody>
              {shown.map(({ lens, k }: { lens: { key: string; name: string }; k: Check }) => (
                <tr key={k.id} style={rowLine}>
                  <td className={`${td} whitespace-nowrap`}>{lens.name.split(" ").slice(-1)[0]}</td>
                  <td className={`${td} num mute whitespace-nowrap`}>{k.id}</td>
                  <td className={td} style={{ minWidth: 220 }}>{k.check}</td>
                  <td className={`${td} num font-semibold`} style={{ color: RESULT[k.result].color }}>{RESULT[k.result].tag}</td>
                  <td className={`${td} num`} style={{ minWidth: 200 }}>{k.shown}</td>
                  <td className={`${td} mute`} style={{ minWidth: 160 }}>{k.source}</td>
                </tr>
              ))}
              {shown.length === 0 && <tr><td className={`${td} mute`} colSpan={6}>No checks match this filter.</td></tr>}
            </tbody>
          </table>
        </Block>
      )}

      <Block open title="Financial figures" note="Latest value, five most recent periods (oldest first), and the filings each is computed from. ≈ marks an approximation.">
        <table className="w-full text-xs border-collapse">
          <thead><tr><Th>Section</Th><Th>Metric</Th><Th right>Latest</Th><Th>Signal</Th><Th>History</Th><Th right>Filings</Th></tr></thead>
          <tbody>
            {figures.map(({ s, f }) => (
              <tr key={`${s.id}.${f.key}`} style={rowLine}>
                <td className={`${td} mute whitespace-nowrap`}>{s.title}</td>
                <td className={td} style={{ minWidth: 180 }}>{f.label}</td>
                <td className={`${td} num text-right font-semibold whitespace-nowrap`}>{f.approx ? "≈ " : ""}{fmtValue(f.unit, f.value)}</td>
                <td className={td} style={{ color: f.tone ? TONE[f.tone].color : "var(--mute)" }}>{f.tone ? TONE[f.tone].word : "–"}</td>
                <td className={`${td} num mute`} style={{ minWidth: 260 }}>{hist(f)}</td>
                <td className={`${td} num text-right mute`}>{f.sources.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Block>

      {(r.risk_flags ?? []).length > 0 && (
        <Block title="Risk screens">
          <table className="w-full text-xs border-collapse">
            <thead><tr><Th>Screen</Th><Th>Signal</Th><Th>Detail</Th><Th right>Value</Th></tr></thead>
            <tbody>
              {r.risk_flags!.map((fl) => (
                <tr key={fl.key} style={rowLine}>
                  <td className={td}>{fl.label}</td>
                  <td className={`${td} font-semibold`} style={{ color: fl.tone ? TONE[fl.tone].color : "var(--mute)" }}>{fl.tone ? TONE[fl.tone].word : "–"}</td>
                  <td className={td}>{fl.detail}</td>
                  <td className={`${td} num text-right`}>{Number.isFinite(fl.value) ? +fl.value.toFixed(3) : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Block>
      )}

      <Block title={`Source filings (${accessions.length})`} note="SEC accession numbers behind the figures and risk screens, newest first. Each links to the filing's folder on EDGAR.">
        <div className="p-3 flex flex-wrap gap-1.5">
          {accessions.map((x) => <a key={x} href={edgar(cik, x)} target="_blank" rel="noreferrer" className="chip num no-underline">{x}</a>)}
        </div>
      </Block>

      <p className="mute text-[11px] m-0">Numbers are computed in Python from filed SEC data and are not written by a model. The investor lenses are rule checks distilled from each investor's published writing; they describe the evidence and the price and are not personal advice or a price target.</p>
    </div>
  );
}
