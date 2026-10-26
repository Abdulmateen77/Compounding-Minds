import { motion } from "framer-motion";
import { Disclosure, Explain, Head } from "../components/Section";
import { jumpTo } from "../route";
import { Say } from "../components/Say";
import { TONE, money, pctOf, type Analysis, type Check, type Lens, type QuickCheck } from "../research";

/* The verdict, the investors, the value, the future: everything here is rendered from the numbers the API
   computed in Python (research/analysis.py). Nothing on this page is written by a model. */

const CHECK = {
  pass: { mark: "✓", color: "var(--success)", word: "Passes" },
  partial: { mark: "~", color: "var(--warning)", word: "Partly" },
  fail: { mark: "✗", color: "var(--error)", word: "Fails" },
  unknown: { mark: "?", color: "var(--muted)", word: "No data" },
} as const;

const fitColor = (fit: number | null) => (fit == null ? "var(--muted)" : fit >= 0.7 ? "var(--success)" : fit >= 0.4 ? "var(--warning)" : "var(--error)");
const usd = (v: number | null | undefined) => (v == null ? "n/a" : `$${v >= 100 ? v.toFixed(0) : v.toFixed(2)}`);

export function Verdict({ a, name }: { a: Analysis; name: string }) {
  const o = a.overall, color = TONE[o.tone].color, v = a.valuation;
  return (
    <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card p-6 md:p-8 grid gap-5"
      style={{ background: `linear-gradient(135deg, color-mix(in srgb, ${color} 12%, var(--card)), var(--card))`, borderColor: `color-mix(in srgb, ${color} 45%, var(--divider))` }}>
      <div>
        <p className="mute text-sm m-0">What the evidence says about {name}</p>
        <h2 className="text-2xl md:text-3xl font-bold my-1" style={{ color }}>{o.headline}</h2>
        <p className="m-0 max-w-3xl leading-relaxed"><Say>{o.why}</Say></p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {a.lenses.map((l) => {
          const c = fitColor(l.fit);
          return (
            <a key={l.key} href={`#lens-${l.key}`} onClick={jumpTo(`lens-${l.key}`)} className="rounded-xl p-3 grid gap-1 no-underline"
              style={{ background: `color-mix(in srgb, ${c} 9%, transparent)`, border: `1px solid color-mix(in srgb, ${c} 35%, var(--divider))`, color: "var(--foreground)" }}>
              <span className="text-xs mute">{l.name}</span>
              <span className="font-semibold">{l.word}</span>
              <span className="text-xs mute"><Say>{l.question}</Say></span>
            </a>
          );
        })}
      </div>
      {v.available && v.position_text && <p className="m-0 text-sm"><b>Price:</b> <Say>{v.position_text}</Say></p>}
      <p className="m-0 text-xs mute">This describes the evidence and the price. It is not personal advice and not a prediction of the share price. Your own goals, time frame and other holdings matter.</p>
    </motion.section>
  );
}

export function Lenses({ lenses }: { lenses: Lens[] }) {
  return (
    <section className="grid gap-4">
      <div>
        <h2 className="text-xl font-semibold m-0">How the investors would read it</h2>
        <p className="mute text-sm m-0 mt-1 max-w-3xl">Each investor's habits of mind, distilled from their own books and written as checks in our own words, run against this company's numbers. Every line cites where the idea comes from.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">{lenses.map((l) => <LensCard key={l.key} l={l} />)}</div>
    </section>
  );
}

function LensCard({ l }: { l: Lens }) {
  const c = fitColor(l.fit);
  return (
    <article id={`lens-${l.key}`} className="card p-5 grid gap-3 content-start">
      <div className="flex items-start justify-between gap-3">
        <div><h3 className="text-lg font-semibold m-0">{l.name}</h3><p className="mute text-sm m-0"><Say>{l.question}</Say></p></div>
        <span className="chip shrink-0" style={{ color: c, borderColor: c }}>{l.word}</span>
      </div>
      {l.note && (
        <div className="rounded-xl p-3 text-sm" style={{ background: "var(--card-alt)" }}>
          <b>Looks like a {l.note.category.toLowerCase()}.</b> <span className="mute"><Say>{l.note.why}</Say>.</span>
        </div>
      )}
      {l.narrative && (
        <div className="grid gap-2">
          <p className="m-0 text-sm leading-relaxed"><Say>{l.narrative}</Say></p>
          {l.ahead && (
            <div className="grid gap-1 pl-3" style={{ borderLeft: "4px solid var(--primary)" }}>
              <span className="text-xs font-semibold">Looking ahead</span>
              <p className="m-0 text-sm leading-relaxed"><Say>{l.ahead}</Say></p>
            </div>
          )}
          <span className="mute text-xs">Summarised by an AI from this investor's books and the checks below. Every number in it is checked against them.</span>
        </div>
      )}
      {l.fit != null && <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--divider)" }}><div style={{ width: `${Math.round(l.fit * 100)}%`, height: "100%", background: c }} /></div>}
      <ul className="m-0 p-0 list-none grid gap-3">{l.checks.map((k) => <CheckRow key={k.id} k={k} />)}</ul>
      <p className="m-0 mute text-xs">
        {l.backtested ? "Tested against what happened next at 50 companies: see below." : "Not back-tested: we hold no historical prices to test the price checks, so treat this view as a way of thinking, not a track record."}
        {l.caveat ? ` ${l.caveat}` : ""}
      </p>
    </article>
  );
}

function CheckRow({ k }: { k: Check }) {
  const C = CHECK[k.result];
  return (
    <li className="flex gap-3 items-start">
      <span aria-label={C.word} className="inline-grid place-items-center w-6 h-6 rounded-full shrink-0 text-xs" style={{ background: `color-mix(in srgb, ${C.color} 14%, transparent)`, color: C.color }}>{C.mark}</span>
      <div className="grid gap-1 text-sm">
        <span className="font-medium"><Say>{k.check}</Say></span>
        <span className="num text-xs">{k.shown}</span>
        <span className="mute text-xs leading-snug">Idea: <Say>{k.principle}</Say>. <i>{k.source}</i></span>
      </div>
    </li>
  );
}

export function Worth({ a }: { a: Analysis }) {
  const v = a.valuation;
  return (
    <section className="grid gap-3">
      <Head title="What could the business be worth per share?" blurb="A cash-flow valuation. It shows what a price assumes; it is not a prediction."
        more={<p className="m-0">Take the free cash it normally produces, grow it for ten years at a rate taken from its own history, discount it back, and add cash less debt.</p>} />
      {!v.available ? <div className="card p-5 text-sm">{v.reason}</div> : (
        <div className="card p-5 grid gap-5">
          <div className="grid gap-3 sm:grid-cols-3">
            {v.scenarios!.map((s) => (
              <div key={s.name} className="rounded-xl p-4 grid gap-1" style={{ background: "var(--card-alt)" }}>
                <span className="text-xs mute"><Say>{`${s.name} case`}</Say></span>
                <span className="num text-2xl font-semibold">{s.value_per_share != null ? usd(s.value_per_share) : money(s.equity_value)}</span>
                {s.value_per_share == null && <span className="mute text-xs">total value of the shares (no reliable share count)</span>}
                <span className="mute text-xs">cash flow grows {pctOf(s.start_growth)} a year at first, fading to {pctOf(v.long_run_growth)}</span>
              </div>
            ))}
          </div>
          {v.price != null && (
            <div className="grid gap-1 text-sm">
              <span><b>Share price today:</b> <span className="num">{usd(v.price)}</span>. <Say>{v.position_text}</Say></span>
              {v.implied_growth != null
                ? <span>To justify today's price, cash flow would have to grow about <b className="num">{pctOf(v.implied_growth)}</b> a year at first, against {pctOf(v.scenarios![1].start_growth)} in the base case.</span>
                : v.position === "above_bull" && <span>No growth rate within a plausible range justifies today's price on this method.</span>}
            </div>
          )}
          {v.sensitivity && (
            <Disclosure level={3} title="What if you require a different yearly return?" summary="Value per share at other required returns">
              <div className="overflow-x-auto">
                <table className="text-sm w-full num" style={{ borderCollapse: "collapse" }}>
                  <caption className="text-left mute text-xs pb-2">Value per share if you require a different yearly return</caption>
                  <thead><tr className="mute text-xs text-left"><th className="py-1 pr-4 font-normal">Required return</th>{v.scenarios!.map((s) => <th key={s.name} className="py-1 pr-4 font-normal">{s.name}</th>)}</tr></thead>
                  <tbody>{v.sensitivity.map((r) => (
                    <tr key={r.rate} style={{ borderTop: "1px solid var(--divider)", fontWeight: Math.abs(r.rate - (v.discount_rate ?? 0)) < 1e-9 ? 600 : 400 }}>
                      <td className="py-1 pr-4">{pctOf(r.rate)}</td>{r.values.map((x, i) => <td key={i} className="py-1 pr-4">{usd(x)}</td>)}
                    </tr>))}</tbody>
                </table>
              </div>
            </Disclosure>
          )}
          <p className="m-0 text-xs mute">Starting cash flow: {money(v.normalised_fcf!)}, the middle value of the last three years so one unusual year does not distort it. A higher required return lowers every value.</p>
        </div>
      )}
    </section>
  );
}

/** The scenario table. `bare` drops the heading when it sits inside another section (the next-five-years block). */
export function Future({ a, bare = false }: { a: Analysis; bare?: boolean }) {
  const f = a.future!;
  const yrs = ["1", "3", "5", "10"];
  return (
    <section className="grid gap-3">
      {!bare && <Head title="What could the next ten years look like?" blurb="Three paths for sales and free cash flow under stated assumptions, not forecasts." />}
      <div className={bare ? "overflow-x-auto" : "card p-5 overflow-x-auto"}>
        <table className="text-sm w-full num" style={{ borderCollapse: "collapse" }}>
          <thead>
            <tr className="mute text-xs text-left">
              <th className="py-1 pr-4 font-normal">Path</th>
              {yrs.map((y) => <th key={y} className="py-1 pr-4 font-normal">In {y} year{y === "1" ? "" : "s"}: sales / free cash</th>)}
            </tr>
          </thead>
          <tbody>
            {f.scenarios.map((s) => (
              <tr key={s.name} style={{ borderTop: "1px solid var(--divider)" }}>
                <td className="py-2 pr-4 font-semibold">{s.name}<div className="mute text-xs font-normal">starts at {pctOf(s.start_growth)} a year</div></td>
                {yrs.map((y) => (
                  <td key={y} className="py-2 pr-4">{s.revenue[y] == null ? "n/a" : money(s.revenue[y] as number)}<span className="mute"> / {s.fcf[y] == null ? "n/a" : money(s.fcf[y] as number)}</span></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* ───────────────────────── has this method worked? ───────────────────────── */

import { useQuery } from "@tanstack/react-query";
import type { Evidence, EvidenceTest } from "../research";

const pc = (x: number | null | undefined, d = 0) => (x == null ? "n/a" : `${(x * 100).toFixed(d)}%`);

function Bars({ t, value, color, fmt }: { t: EvidenceTest; value: (b: EvidenceTest["buckets"][number]) => number | null; color: string; fmt: (x: number | null) => string }) {
  const vals = t.buckets.map(value), top = Math.max(...vals.map((v) => v ?? 0), 0.0001);
  const names = ["Passes most checks", "Passes some", "Passes few"];
  return (
    <div className="grid gap-2">
      {t.buckets.map((b, i) => (
        <div key={b.bucket} className="grid grid-cols-[9rem_1fr_3.5rem] items-center gap-3 text-sm">
          <span className="text-xs">{names[i]} <span className="mute">({b.n})</span></span>
          <div className="h-3 rounded-full overflow-hidden" style={{ background: "var(--divider)" }}>
            <div style={{ width: `${Math.max(((vals[i] ?? 0) / top) * 100, 1.5)}%`, height: "100%", background: color }} />
          </div>
          <span className="num font-semibold text-right">{fmt(vals[i])}</span>
        </div>
      ))}
    </div>
  );
}

export function EvidencePanel() {
  const q = useQuery({ queryKey: ["evidence"], retry: 0, staleTime: Infinity, queryFn: async (): Promise<Evidence> => { const r = await fetch("/api/research/evidence"); if (!r.ok) throw new Error(); return r.json(); } });
  if (q.isLoading) return <p className="mute text-sm m-0" role="status">Loading the results…</p>;
  if (!q.data) return <p className="mute text-sm m-0">The back-test results are not available right now.</p>;
  const e = q.data, all = e.all_quarters.tests, ye = e.year_end_only.tests, ho = e.held_out_year_end.tests;
  const find = (ts: EvidenceTest[], lens: string, k: string) => ts.find((t) => t.lens === lens && t.outcome.startsWith(k))!;
  const hoM = ho.find((t) => t.lens === "munger");
  const m = find(all, "munger", "Auditor"), b = find(all, "buffett", "Free-cash"), g = find(all, "buffett", "Revenue");
  return (
    <section className="grid gap-3">
      <Head title="Have these checks actually worked?" blurb={`We ran the same checks on 50 large US companies at every quarter from 2018 to 2023, using only the filings public at the time, and compared them with what happened over the next twelve months (${e.all_quarters.rows.toLocaleString()} company-quarters, no AI involved).`} />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="card p-5 grid gap-3 content-start">
          <span className="font-semibold">Munger's “how could it fail?” checks</span>
          <span className="mute text-xs">Share of companies that cut the dividend or changed auditor within the next year</span>
          <Bars t={m} value={(x) => x.mean} color="var(--error)" fmt={(x) => pc(x, 1)} />
          <p className="m-0 text-sm">
            In the right direction, but modest: companies passing few of the checks had one of these events in {pc(m.buckets[2].mean, 0)} of cases, against {pc(m.buckets[0].mean, 0)} for those passing most. These events are rare, so the group passing few is small ({m.buckets[2].n} cases).
            {" "}{hoM && hoM.p != null && hoM.p < 0.05 ? `It also holds on the 10 companies kept out of everything else (rank correlation ${hoM.spearman?.toFixed(2)}).` : `On the 10 held-out companies there are too few cases to tell either way.`}
          </p>
        </div>
        <div className="card p-5 grid gap-3 content-start">
          <span className="font-semibold">Buffett's “quality” checks</span>
          <span className="mute text-xs">Typical free-cash-flow margin a year later (median)</span>
          <Bars t={b} value={(x) => x.median} color="var(--success)" fmt={(x) => pc(x, 1)} />
          <p className="m-0 text-sm">Companies passing most of the checks kept earning more cash per dollar of sales. But the same checks said nothing about sales growth: typical growth was {pc(g.buckets[0].median, 1)}, {pc(g.buckets[1].median, 1)} and {pc(g.buckets[2].median, 1)}, with no pattern.</p>
        </div>
      </div>
      <Explain label="Read the caveats"><ul className="m-0 pl-5 grid gap-1 max-w-3xl">
        <li>This tests whether the checks tell good businesses from weak ones. It does not test whether the share price rose, and it does not test the price and valuation checks (we hold no historical prices).</li>
        <li>The cash-flow check overlaps with what it predicts, so its result shows persistence, not independent proof.</li>
        <li>Windows overlap from quarter to quarter. Using one window per company per year gives the same direction (Munger {ye.find((t) => t.lens === "munger")?.spearman?.toFixed(2)}, Buffett cash {ye.find((t) => t.lens === "buffett" && t.outcome.startsWith("Free-cash"))?.spearman?.toFixed(2)}).</li>
        <li>Large US companies, 2018 to 2023, includes the 2020 shock. Past performance of a method is no guarantee.</li>
      </ul></Explain>
    </section>
  );
}

/* ───────────────────────── the 5-minute check ───────────────────────── */

export function QuickCheckBlock({ q }: { q: QuickCheck }) {
  const color = q.score == null ? "var(--muted)" : q.score >= 0.75 ? "var(--success)" : q.score >= 0.4 ? "var(--warning)" : "var(--error)";
  return (
    <section className="grid gap-3">
      <Head title="The 5-minute check: is it worth researching further?" blurb="Five quick tests that filter out companies to avoid. Meant for manufacturing and other non-financial companies." />
      {!q.applies ? <div className="card p-5 text-sm max-w-3xl">{q.note}</div> : (
        <div className="card p-5 grid gap-4 max-w-3xl">
          {q.verdict && <p className="m-0 text-lg font-semibold" style={{ color }}>{q.verdict}</p>}
          <ul className="m-0 p-0 list-none grid gap-3">
            {q.items.map((i) => {
              const C = CHECK[i.result];
              return (
                <li key={i.key} className="flex gap-3 items-start">
                  <span aria-label={C.word} className="inline-grid place-items-center w-6 h-6 rounded-full shrink-0 text-xs" style={{ background: `color-mix(in srgb, ${C.color} 14%, transparent)`, color: C.color }}>{C.mark}</span>
                  <div className="grid gap-1 text-sm">
                    <span className="font-medium"><Say>{i.label}</Say>: <span className="font-normal">{i.found}</span></span>
                    <span className="mute text-xs">Look for: <Say>{i.rule}</Say></span>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="m-0 mute text-xs">{q.note} Source: {q.source}.</p>
        </div>
      )}
    </section>
  );
}
