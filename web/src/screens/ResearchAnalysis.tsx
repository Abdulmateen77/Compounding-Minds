import { motion } from "framer-motion";
import { TONE, money, pctOf, type Analysis, type Check, type Lens, type QuickCheck } from "../research";

/* The verdict, the four investors, the value, the future: everything here is rendered from the numbers the API
   computed in Python (research/analysis.py). Nothing on this page is written by a model. */

const CHECK = {
  pass: { mark: "✓", color: "var(--green)", word: "Passes" },
  partial: { mark: "~", color: "var(--amber)", word: "Partly" },
  fail: { mark: "✗", color: "var(--red)", word: "Fails" },
  unknown: { mark: "?", color: "var(--mute)", word: "No data" },
} as const;

const fitColor = (fit: number | null) => (fit == null ? "var(--mute)" : fit >= 0.7 ? "var(--green)" : fit >= 0.4 ? "var(--amber)" : "var(--red)");
const usd = (v: number | null | undefined) => (v == null ? "n/a" : `$${v >= 100 ? v.toFixed(0) : v.toFixed(2)}`);

export function Verdict({ a, name }: { a: Analysis; name: string }) {
  const o = a.overall, color = TONE[o.tone].color, v = a.valuation;
  return (
    <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="card p-6 md:p-8 grid gap-5"
      style={{ background: `linear-gradient(135deg, color-mix(in srgb, ${color} 12%, var(--panel)), var(--panel))`, borderColor: `color-mix(in srgb, ${color} 45%, var(--line))` }}>
      <div>
        <p className="mute text-sm m-0">What the evidence says about {name}</p>
        <h2 className="text-2xl md:text-3xl font-bold tracking-tight my-1" style={{ color }}>{o.headline}</h2>
        <p className="m-0 max-w-3xl leading-relaxed">{o.why}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {a.lenses.map((l) => {
          const c = fitColor(l.fit);
          return (
            <a key={l.key} href={`#lens-${l.key}`} className="rounded-xl p-3 grid gap-1 no-underline"
              style={{ background: `color-mix(in srgb, ${c} 9%, transparent)`, border: `1px solid color-mix(in srgb, ${c} 35%, var(--line))`, color: "var(--text)" }}>
              <span className="text-xs mute">{l.name}</span>
              <span className="font-semibold">{l.word}</span>
              <span className="text-xs mute">{l.question}</span>
            </a>
          );
        })}
      </div>
      {v.available && v.position_text && <p className="m-0 text-sm"><b>Price:</b> {v.position_text}</p>}
      <p className="m-0 text-xs mute">This describes the evidence and the price. It is not personal advice and not a prediction of the share price. Your own goals, time frame and other holdings matter.</p>
    </motion.section>
  );
}

export function Lenses({ lenses }: { lenses: Lens[] }) {
  return (
    <section className="grid gap-4">
      <div>
        <h2 className="text-xl font-semibold m-0">How six great investors would read it</h2>
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
        <div><h3 className="text-lg font-semibold m-0">{l.name}</h3><p className="mute text-sm m-0">{l.question}</p></div>
        <span className="chip shrink-0" style={{ color: c, borderColor: c }}>{l.word}</span>
      </div>
      {l.note && (
        <div className="rounded-xl p-3 text-sm" style={{ background: "var(--panel2)" }}>
          <b>Looks like a {l.note.category.toLowerCase()}.</b> <span className="mute">{l.note.why}.</span>
        </div>
      )}
      {l.narrative && (
        <div className="grid gap-2">
          <p className="m-0 text-sm leading-relaxed">{l.narrative}</p>
          {l.ahead && (
            <div className="grid gap-1 pl-3" style={{ borderLeft: "3px solid var(--blue)" }}>
              <span className="text-xs font-semibold">Looking ahead</span>
              <p className="m-0 text-sm leading-relaxed">{l.ahead}</p>
            </div>
          )}
          <span className="mute text-[11px]">Summarised by an AI from this investor's books and the checks below. Every number in it is checked against them.</span>
        </div>
      )}
      {l.fit != null && <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--line)" }}><div style={{ width: `${Math.round(l.fit * 100)}%`, height: "100%", background: c }} /></div>}
      <ul className="m-0 p-0 list-none grid gap-3">{l.checks.map((k) => <CheckRow key={k.id} k={k} />)}</ul>
      <p className="m-0 mute text-[11px]">
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
      <span aria-label={C.word} className="inline-grid place-items-center w-6 h-6 rounded-full shrink-0 text-xs" style={{ background: `color-mix(in srgb, ${C.color} 20%, transparent)`, color: C.color }}>{C.mark}</span>
      <div className="grid gap-0.5 text-sm">
        <span className="font-medium">{k.check}</span>
        <span className="num text-xs">{k.shown}</span>
        <span className="mute text-xs leading-snug">Idea: {k.principle}. <i>{k.source}</i></span>
      </div>
    </li>
  );
}

export function Worth({ a }: { a: Analysis }) {
  const v = a.valuation;
  return (
    <section className="grid gap-3">
      <div>
        <h2 className="text-xl font-semibold m-0">What could the business be worth per share?</h2>
        <p className="mute text-sm m-0 mt-1 max-w-3xl">A cash-flow valuation: take the free cash it normally produces, grow it for ten years at a rate taken from its own history, discount it back, and add cash less debt. It shows what a price assumes. It is not a prediction.</p>
      </div>
      {!v.available ? <div className="card p-5 text-sm">{v.reason}</div> : (
        <div className="card p-5 grid gap-5">
          <div className="grid gap-3 sm:grid-cols-3">
            {v.scenarios!.map((s) => (
              <div key={s.name} className="rounded-xl p-4 grid gap-1" style={{ background: "var(--panel2)" }}>
                <span className="text-xs mute">{s.name} case</span>
                <span className="num text-2xl font-semibold">{s.value_per_share != null ? usd(s.value_per_share) : money(s.equity_value)}</span>
                {s.value_per_share == null && <span className="mute text-xs">total value of the shares (no reliable share count)</span>}
                <span className="mute text-xs">cash flow grows {pctOf(s.start_growth)} a year at first, fading to {pctOf(v.long_run_growth)}</span>
              </div>
            ))}
          </div>
          {v.price != null && (
            <div className="grid gap-1 text-sm">
              <span><b>Share price today:</b> <span className="num">{usd(v.price)}</span>. {v.position_text}</span>
              {v.implied_growth != null
                ? <span>To justify today's price, cash flow would have to grow about <b className="num">{pctOf(v.implied_growth)}</b> a year at first, against {pctOf(v.scenarios![1].start_growth)} in the base case.</span>
                : v.position === "above_bull" && <span>No growth rate within a plausible range justifies today's price on this method.</span>}
            </div>
          )}
          {v.sensitivity && (
            <div className="overflow-x-auto">
              <table className="text-sm w-full num" style={{ borderCollapse: "collapse" }}>
                <caption className="text-left mute text-xs pb-2">Value per share if you require a different yearly return</caption>
                <thead><tr className="mute text-xs text-left"><th className="py-1 pr-4 font-normal">Required return</th>{v.scenarios!.map((s) => <th key={s.name} className="py-1 pr-4 font-normal">{s.name}</th>)}</tr></thead>
                <tbody>{v.sensitivity.map((r) => (
                  <tr key={r.rate} style={{ borderTop: "1px solid var(--line)", fontWeight: Math.abs(r.rate - (v.discount_rate ?? 0)) < 1e-9 ? 600 : 400 }}>
                    <td className="py-1 pr-4">{pctOf(r.rate)}</td>{r.values.map((x, i) => <td key={i} className="py-1 pr-4">{usd(x)}</td>)}
                  </tr>))}</tbody>
              </table>
            </div>
          )}
          <p className="m-0 text-xs mute">Starting cash flow: {money(v.normalised_fcf!)}, the middle value of the last three years so one unusual year does not distort it. A higher required return lowers every value.</p>
        </div>
      )}
    </section>
  );
}

export function Future({ a, outlook }: { a: Analysis; outlook: string[] }) {
  const f = a.future!;
  const yrs = ["1", "3", "5", "10"];
  return (
    <section className="grid gap-3">
      <div>
        <h2 className="text-xl font-semibold m-0">What could the next ten years look like?</h2>
        <p className="mute text-sm m-0 mt-1 max-w-3xl">Three paths for sales and free cash flow. Each grows at a starting rate taken from the company's own record, then slows toward the economy's long-run pace. These are scenarios under stated assumptions, not forecasts.</p>
      </div>
      <div className="card p-5 overflow-x-auto">
        <table className="text-sm w-full num" style={{ borderCollapse: "collapse" }}>
          <thead>
            <tr className="mute text-xs text-left">
              <th className="py-1 pr-4 font-normal">Path</th>
              {yrs.map((y) => <th key={y} className="py-1 pr-4 font-normal">In {y} year{y === "1" ? "" : "s"}: sales / free cash</th>)}
            </tr>
          </thead>
          <tbody>
            {f.scenarios.map((s) => (
              <tr key={s.name} style={{ borderTop: "1px solid var(--line)" }}>
                <td className="py-2 pr-4 font-semibold">{s.name}<div className="mute text-[11px] font-normal">starts at {pctOf(s.start_growth)} a year</div></td>
                {yrs.map((y) => (
                  <td key={y} className="py-2 pr-4">{s.revenue[y] == null ? "n/a" : money(s.revenue[y] as number)}<span className="mute"> / {s.fcf[y] == null ? "n/a" : money(s.fcf[y] as number)}</span></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {outlook.length > 0 && (
        <div className="card p-5 grid gap-2">
          <span className="font-semibold text-sm">What management itself expects</span>
          {outlook.map((t) => <blockquote key={t} className="m-0 pl-3 text-sm leading-relaxed" style={{ borderLeft: "3px solid var(--blue)" }}>{t}</blockquote>)}
        </div>
      )}
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
          <div className="h-3 rounded-full overflow-hidden" style={{ background: "var(--line)" }}>
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
  if (!q.data) return null;
  const e = q.data, all = e.all_quarters.tests, ye = e.year_end_only.tests, ho = e.held_out_year_end.tests;
  const find = (ts: EvidenceTest[], lens: string, k: string) => ts.find((t) => t.lens === lens && t.outcome.startsWith(k))!;
  const hoM = ho.find((t) => t.lens === "munger");
  const m = find(all, "munger", "Auditor"), b = find(all, "buffett", "Free-cash"), g = find(all, "buffett", "Revenue");
  return (
    <section className="grid gap-3">
      <div>
        <h2 className="text-xl font-semibold m-0">Have these checks actually worked?</h2>
        <p className="mute text-sm m-0 mt-1 max-w-3xl">We ran the same checks on 50 large US companies at every quarter from 2018 to 2023, using only the filings public at the time, and compared them with what happened over the next twelve months. {e.all_quarters.rows.toLocaleString()} company-quarters, no AI involved, repeatable.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="card p-5 grid gap-3 content-start">
          <span className="font-semibold">Munger's “how could it fail?” checks</span>
          <span className="mute text-xs">Share of companies that cut the dividend or changed auditor within the next year</span>
          <Bars t={m} value={(x) => x.mean} color="var(--red)" fmt={(x) => pc(x, 1)} />
          <p className="m-0 text-sm">
            In the right direction, but modest: companies passing few of the checks had one of these events in {pc(m.buckets[2].mean, 0)} of cases, against {pc(m.buckets[0].mean, 0)} for those passing most. These events are rare, so the group passing few is small ({m.buckets[2].n} cases).
            {" "}{hoM && hoM.p != null && hoM.p < 0.05 ? `It also holds on the 10 companies kept out of everything else (rank correlation ${hoM.spearman?.toFixed(2)}).` : `On the 10 held-out companies there are too few cases to tell either way.`}
          </p>
        </div>
        <div className="card p-5 grid gap-3 content-start">
          <span className="font-semibold">Buffett's “quality” checks</span>
          <span className="mute text-xs">Typical free-cash-flow margin a year later (median)</span>
          <Bars t={b} value={(x) => x.median} color="var(--green)" fmt={(x) => pc(x, 1)} />
          <p className="m-0 text-sm">Companies passing most of the checks kept earning more cash per dollar of sales. But the same checks said nothing about sales growth: typical growth was {pc(g.buckets[0].median, 1)}, {pc(g.buckets[1].median, 1)} and {pc(g.buckets[2].median, 1)}, with no pattern.</p>
        </div>
      </div>
      <ul className="mute text-xs m-0 pl-5 grid gap-1 max-w-3xl">
        <li>This tests whether the checks tell good businesses from weak ones. It does not test whether the share price rose, and it does not test the price and valuation checks (we hold no historical prices).</li>
        <li>The cash-flow check overlaps with what it predicts, so its result shows persistence, not independent proof.</li>
        <li>Windows overlap from quarter to quarter. Using one window per company per year gives the same direction (Munger {ye.find((t) => t.lens === "munger")?.spearman?.toFixed(2)}, Buffett cash {ye.find((t) => t.lens === "buffett" && t.outcome.startsWith("Free-cash"))?.spearman?.toFixed(2)}).</li>
        <li>Large US companies, 2018 to 2023, includes the 2020 shock. Past performance of a method is no guarantee.</li>
      </ul>
    </section>
  );
}

/* ───────────────────────── the 5-minute check ───────────────────────── */

export function QuickCheckBlock({ q }: { q: QuickCheck }) {
  const color = q.score == null ? "var(--mute)" : q.score >= 0.75 ? "var(--green)" : q.score >= 0.4 ? "var(--amber)" : "var(--red)";
  return (
    <section className="grid gap-3">
      <div>
        <h2 className="text-xl font-semibold m-0">The 5-minute check: is it worth researching further?</h2>
        <p className="mute text-sm m-0 mt-1 max-w-3xl">Five quick tests that filter out companies to avoid before you spend time on them. Meant for manufacturing and other non-financial companies.</p>
      </div>
      {!q.applies ? <div className="card p-5 text-sm">{q.note}</div> : (
        <div className="card p-5 grid gap-4">
          {q.verdict && <p className="m-0 text-lg font-semibold" style={{ color }}>{q.verdict}</p>}
          <ul className="m-0 p-0 list-none grid gap-3">
            {q.items.map((i) => {
              const C = CHECK[i.result];
              return (
                <li key={i.key} className="flex gap-3 items-start">
                  <span aria-label={C.word} className="inline-grid place-items-center w-6 h-6 rounded-full shrink-0 text-xs" style={{ background: `color-mix(in srgb, ${C.color} 20%, transparent)`, color: C.color }}>{C.mark}</span>
                  <div className="grid gap-0.5 text-sm">
                    <span className="font-medium">{i.label}: <span className="font-normal">{i.found}</span></span>
                    <span className="mute text-xs">Look for: {i.rule}</span>
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
