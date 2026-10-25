/** Plain-English layer for the verdict screen: metric names, what each analyst's question means,
 * and how an answer reads as a signal. Display only: every number still comes from the API. */

export type Signal = "good" | "warn" | "neutral";

type Fmt = (v: number) => string;
const pct: Fmt = (v) => `${(v * 100).toFixed(1)}%`;
const pts: Fmt = (v) => `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)} pts`;
const times: Fmt = (v) => `${v.toFixed(1)}×`;
const count: Fmt = (v) => `${Math.round(v)}`;

export const METRICS: Record<string, { label: string; meaning: string; fmt: Fmt }> = {
  // Buffett: cash and profitability
  fcf_margin_ttm: { label: "Free-cash-flow margin", meaning: "Cash left from each dollar of sales after paying for investment, last 12 months", fmt: pct },
  fcf_margin_qoq_change: { label: "Change in cash margin", meaning: "How the free-cash-flow margin moved since last quarter", fmt: pts },
  operating_margin: { label: "Operating margin", meaning: "Profit from the core business per dollar of sales", fmt: pct },
  roic: { label: "Return on capital", meaning: "Profit earned on the money invested in the business", fmt: pct },
  debt_to_ebitda: { label: "Debt vs earnings", meaning: "Years of operating earnings it would take to pay off debt", fmt: times },
  fcf_slope_8q: { label: "Two-year cash trend", meaning: "Direction of the cash margin over 8 quarters, per quarter", fmt: pts },
  capex_to_revenue: { label: "Investment spending", meaning: "Spending on plant and equipment as a share of sales", fmt: pct },
  // Munger: financial trouble
  interest_coverage: { label: "Interest cover", meaning: "How many times earnings cover the interest bill (under 2× is thin)", fmt: times },
  current_ratio: { label: "Short-term cushion", meaning: "Short-term assets divided by bills due within a year", fmt: times },
  cash_runway_quarters: { label: "Cash runway", meaning: "Quarters the cash would last at the current burn; 40 means it is not burning cash", fmt: (v) => `${Math.round(v)} quarters` },
  dividend_cut_history_5y: { label: "Dividend cuts, 5 years", meaning: "Times the dividend was cut in the last five years", fmt: count },
  auditor_changes_5y: { label: "Auditor changes, 5 years", meaning: "Times the company changed auditor in the last five years", fmt: count },
  going_concern_hits: { label: "Going-concern warnings", meaning: "Auditor doubts about survival found in filings", fmt: count },
  leverage_trend_8q: { label: "Debt-load trend", meaning: "Is debt rising faster than earnings? Change per quarter over two years", fmt: (v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}× / q` },
  // Dalio: revenue outlook and the economy
  revenue_growth_yoy: { label: "Revenue growth", meaning: "Sales over the last 12 months versus the 12 before", fmt: pct },
  revenue_growth_mean_5y: { label: "Five-year average growth", meaning: "Typical yearly revenue growth over five years", fmt: pct },
  revenue_growth_std_5y: { label: "Growth swings", meaning: "How much yearly growth varies: higher means less predictable", fmt: pct },
  revenue_macro_beta: { label: "Sensitivity to the economy", meaning: "How strongly sales have moved with US GDP (1 = in step)", fmt: times },
  gdp_growth_yoy: { label: "US economic growth", meaning: "Real GDP growth versus a year earlier, as first reported", fmt: pct },
  unemployment_rate: { label: "US unemployment", meaning: "Unemployment rate as known at the time", fmt: pct },
  yield_curve_10y_2y: { label: "Yield curve", meaning: "10-year minus 2-year Treasury rate; below zero often precedes slowdowns", fmt: pts },
  credit_spread_baa: { label: "Corporate credit spread", meaning: "Extra interest companies pay over Treasuries; rising means stress", fmt: pts },
};

export const metricLabel = (name: string) => METRICS[name]?.label ?? name.replaceAll("_", " ");
export const metricValue = (name: string, v: number) => (METRICS[name] ? METRICS[name].fmt(v) : String(+v.toFixed(3)));

type AgentPlain = {
  topic: string;
  question: string;
  answers: Record<string, { text: string; signal: Signal; clause: string }>;
};

export const AGENTS: Record<string, AgentPlain> = {
  fundamentals: {
    topic: "Cash and profit",
    question: "Will cash flow and profit margins both improve next quarter?",
    answers: {
      yes: { text: "Yes, both should improve", signal: "good", clause: "cash and margins to improve" },
      no: { text: "No, not both", signal: "warn", clause: "cash and margins to stall" },
    },
  },
  risk: {
    topic: "Financial trouble",
    question: "Will the company hit trouble in the next 12 months: a dividend cut, an auditor change or a going-concern warning?",
    answers: {
      no: { text: "No trouble expected", signal: "good", clause: "no financial trouble" },
      yes: { text: "Trouble likely", signal: "warn", clause: "a real risk of financial trouble" },
    },
  },
  scenarios: {
    topic: "Revenue outlook",
    question: "Where will revenue land over the next four quarters?",
    answers: {
      bull: { text: "Strong growth, 10% or more", signal: "good", clause: "revenue to grow strongly" },
      base: { text: "Modest growth, 0 to 10%", signal: "neutral", clause: "revenue to grow modestly" },
      bear: { text: "Shrinking, below 0%", signal: "warn", clause: "revenue to shrink" },
    },
  },
};

export const SIGNAL = {
  good: { word: "Good sign", color: "var(--success)" },
  warn: { word: "Warning sign", color: "var(--error)" },
  neutral: { word: "Neutral", color: "var(--warning)" },
} as const;

export function plainAnswer(agent: string, answer: string) {
  return AGENTS[agent]?.answers[answer] ?? { text: answer, signal: "neutral" as Signal, clause: answer };
}

/** "fcf_margin_qoq_change is negative (-0.0123)" -> "Change in cash margin is negative (-0.0123)". */
export function humanize(text: string): string {
  return text
    .replace(/\b([a-z]+(?:_[a-z0-9]+)+)\b/g, (m) => (METRICS[m] ? METRICS[m].label.toLowerCase() : m.replaceAll("_", " ")))
    .replace(/\b(buffett|munger|dalio|graham|moat)\.0?(\d+)\b/gi, (_, who: string, n: string) => `${who[0].toUpperCase()}${who.slice(1)} rule ${n}`);
}

export const longDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

export function certainty(c: number) {
  if (c >= 0.7) return "High certainty";
  if (c >= 0.45) return "Moderate certainty";
  return "Low certainty";
}

export const HEADLINE = {
  investable: { text: "The evidence leans positive", sub: "Most of what the filings show points the right way." },
  watch: { text: "Mixed evidence: worth watching", sub: "The signals disagree, so the filings don't make a clear case either way." },
  not_investable: { text: "The evidence leans negative", sub: "Most of what the filings show points the wrong way." },
} as const;

/** One sentence that names each analyst's view, good news last when the overall picture is negative. */
export function bottomLine(views: { agent: string; investor: string; answer: string }[]): string {
  const parts = views.filter((v) => AGENTS[v.agent]).map((v) => ({ v, p: plainAnswer(v.agent, v.answer) }));
  const say = (x: (typeof parts)[number]) => `${x.v.investor} expects ${x.p.clause}`;
  const warn = parts.filter((x) => x.p.signal === "warn"), rest = parts.filter((x) => x.p.signal !== "warn");
  if (!warn.length || !rest.length) return `${parts.map(say).join(", ")}.`.replace(/, ([^,]*)$/, " and $1");
  const join = (xs: typeof parts) => xs.map(say).join(" and ");
  return `${join(warn)}, while ${join(rest)}.`;
}
