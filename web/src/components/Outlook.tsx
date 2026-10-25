import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { TONE, type Market, type Outlook } from "../research";

const pct = (x: number | null | undefined, d = 0) => (x == null ? "n/a" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)}%`);
const usd = (v: number | null | undefined) => (v == null ? "n/a" : `$${v >= 100 ? v.toFixed(0) : v.toFixed(2)}`);

/** The next five years: how likely the business is to be bigger (from its own record), the value per share along the way under
    the three cases beside the share price so far, and one plain reading. A value path, not a share-price forecast. */
export function OutlookBlock({ o, market }: { o: Outlook; market?: Market | null }) {
  const v = o.verdict, color = TONE[v.tone].color, odds = o.odds;
  const thisYear = new Date().getFullYear();
  const past = (market?.history ?? []).filter((h, i, arr) => i % 3 === 0 || i === arr.length - 1).slice(-21)   // quarterly, five years
    .map((h) => ({ t: Number(h.date.slice(0, 4)) + (Number(h.date.slice(5, 7)) - 1) / 12, Price: h.close }));
  const future = o.value_path.length ? o.value_path[0].points.map((p, i) => ({
    t: thisYear + p.year + (new Date().getMonth()) / 12,
    Bear: o.value_path[0].points[i].value, Base: o.value_path[1]?.points[i].value, Bull: o.value_path[2]?.points[i].value,
    ...(i === 0 && market ? { Price: market.price } : {}),
  })) : [];
  const rows = [...past, ...future].sort((a, b) => a.t - b.t);

  return (
    <section className="grid gap-3">
      <div>
        <h2 className="text-xl font-semibold m-0">The next five years</h2>
        <p className="mute text-sm m-0 mt-1 max-w-3xl">Where the business could be, and what that would make each share worth, worked out from every figure above. It is a view of the business's value, not a forecast of the share price, which can stay far from value for years.</p>
      </div>
      <div className="card p-5 grid gap-5" style={{ borderColor: `color-mix(in srgb, ${color} 40%, var(--line))` }}>
        <div className="grid gap-1">
          <p className="m-0 text-lg font-semibold" style={{ color }}>{v.headline}</p>
          <p className="m-0 text-sm leading-relaxed max-w-3xl">{v.why}</p>
        </div>

        {odds && (
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat big={`${Math.min(99, Math.round(odds.chance_higher * 100))}%`} label="chance sales are higher in five years" />
            <Stat big={pct(odds.median_change)} label={`typical five-year change in sales (one in ten: ${pct(odds.low_change)} or worse, ${pct(odds.high_change)} or better)`} />
            <Stat big={`${Math.round(odds.chance_down_a_fifth * 100)}%`} label="chance sales fall by a fifth or more" />
          </div>
        )}

        {rows.length > 1 && (
          <div className="grid gap-2">
            <span className="text-sm font-medium">Share price so far, and value per share for the next five years</span>
            <div style={{ height: 300 }}>
              <ResponsiveContainer>
                <LineChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--line)" vertical={false} />
                  <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(t) => String(Math.floor(t))} stroke="var(--mute)" fontSize={12} />
                  <YAxis stroke="var(--mute)" fontSize={12} tickFormatter={(x) => `$${Math.round(x)}`} width={56} />
                  <Tooltip formatter={(x) => usd(Number(x))} labelFormatter={(t) => String(Math.floor(Number(t)))} contentStyle={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 12 }} />
                  <Legend />
                  <Line dataKey="Price" stroke="var(--text)" dot={false} strokeWidth={2} connectNulls />
                  <Line dataKey="Bull" stroke="var(--green)" dot={false} strokeDasharray="5 4" connectNulls />
                  <Line dataKey="Base" stroke="var(--blue)" dot={false} strokeWidth={2.5} connectNulls />
                  <Line dataKey="Bear" stroke="var(--red)" dot={false} strokeDasharray="5 4" connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <p className="m-0 mute text-xs">Dashed and solid lines are the business's value per share under the bear, base and bull growth cases (the valuation section's model, read at each year). The line on the left is the actual share price.</p>
          </div>
        )}

        <div className="grid gap-1 text-xs mute">
          {odds && <span>How the odds are worked out: five years of sales growth are drawn, many thousands of times, from the {odds.history_years} yearly growth rates this company has actually had (best {pct(odds.best_year, 1)}, worst {pct(odds.worst_year, 1)}). Its own record is the only input, so an uneven record gives a wide range.</span>}
          {o.base_value_in_5y != null && <span>Base-case value per share in five years: {usd(o.base_value_in_5y)} against {usd(o.price)} today.</span>}
          <span>Research tool, not financial advice.</span>
        </div>
      </div>
    </section>
  );
}

function Stat({ big, label }: { big: string; label: string }) {
  return (
    <div className="rounded-xl p-4 grid gap-1" style={{ background: "var(--panel2)" }}>
      <span className="num text-2xl font-semibold">{big}</span>
      <span className="mute text-xs leading-snug">{label}</span>
    </div>
  );
}
