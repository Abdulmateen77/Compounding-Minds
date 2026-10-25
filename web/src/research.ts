/** Types and number formatting for the research report (research/report.py is the source of truth). */

export type Tone = "good" | "watch" | "warn" | null;

export type Figure = {
  key: string; label: string; meaning: string; unit: string; value: number | null; approx: boolean; tone: Tone;
  history: { end: string; value: number | null }[]; sources: string[];
};
export type Flag = { key: string; label: string; value: number; detail: string; tone: Tone; meaning: string; sources: string[] };
export type Section = { id: string; title: string; figures: Figure[]; reading: string[] };
export type Market = {
  price: number; currency: string; price_date: string; symbol: string; high_52w: number | null; low_52w: number | null;
  history: { date: string; close: number }[]; shares?: number; shares_as_of?: string; market_cap?: number; enterprise_value?: number;
  pe?: number | null; ev_to_ebitda?: number | null; price_to_sales?: number | null; fcf_yield?: number | null; dividend_yield?: number | null;
};
export type Plans = {
  source: { form: string; filed: string; accession: string; url: string };
  about: string | null; strategy: string[]; rnd: string[]; outlook: string[]; going_concern_hits: number;
};
export type Report = {
  supported: boolean; reason?: string;
  company: { name: string; ticker: string | null; exchange: string | null; market: string; cik: number };
  as_of?: string; data_through?: string; generated_at?: string; sec_url?: string;
  scorecard?: Figure[]; tally?: { good: number; watch: number; warn: number };
  sections?: Section[]; risk_flags?: Flag[];
  economy?: { key: string; label: string; meaning: string; unit: string; value: number }[];
  market?: Market | null; plans?: Plans | null; notes?: string[]; missing?: string[]; analysis?: Analysis; news?: News | null; quick_check?: QuickCheck; outlook?: Outlook;
  latest_filing?: { form: string; filed: string; period: string | null; accession: string | null } | null; facts_through?: string | null; checked_at?: string;
};
export type Check = { id: string; principle: string; source: string; check: string; result: "pass" | "partial" | "fail" | "unknown"; shown: string };
export type Lens = { key: string; name: string; question: string; fit: number | null; word: string; checks: Check[]; narrative?: string | null; ahead?: string | null; note?: { category: string; why: string }; backtested?: boolean; caveat?: string | null; looks_for?: string[]; book?: string | null; decision?: Decision };
export type Scenario = { name: string; start_growth: number; value_per_share: number | null; equity_value: number; fcf_path: number[]; revenue_path: number[] | null };
export type Valuation = {
  available: boolean; reason?: string; normalised_fcf?: number; discount_rate?: number; long_run_growth?: number; years?: number;
  scenarios?: Scenario[]; sensitivity?: { rate: number; values: (number | null)[] }[]; price?: number; implied_growth?: number | null;
  price_vs_base?: number | null; position?: string; position_text?: string;
};
export type Future = { scenarios: { name: string; start_growth: number; value_per_share: number | null; revenue: Record<string, number | null>; fcf: Record<string, number | null> }[] };
export type Overall = { key: string; tone: "good" | "watch" | "warn"; headline: string; why: string };
export type Analysis = { valuation: Valuation; lenses: Lens[]; overall: Overall; future: Future | null; panel?: PanelTally };
export type Candidate = { cik: number; name: string; ticker: string; exchange: string | null; market: string };
export type SearchResult = { query: string; results: Candidate[]; message: string | null };

export const TONE = {
  good: { word: "Strength", color: "var(--green)" },
  watch: { word: "Worth watching", color: "var(--amber)" },
  warn: { word: "Concern", color: "var(--red)" },
} as const;

export function money(v: number, digits = 1): string {
  const a = Math.abs(v), sign = v < 0 ? "-" : "";
  if (a >= 1e12) return `${sign}$${(a / 1e12).toFixed(2)}T`;
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(digits)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(0)}M`;
  return `${sign}$${a.toFixed(0)}`;
}

export function fmtValue(unit: string, v: number | null): string {
  if (v == null) return "not reported";
  switch (unit) {
    case "usd": return money(v);
    case "pct": return `${(v * 100).toFixed(1)}%`;
    case "x": return `${v.toFixed(2)}×`;
    case "count": return String(Math.round(v));
    case "quarters": return `${Math.round(v)} quarters`;
    default: return String(+v.toFixed(3));
  }
}

export const year = (iso: string) => iso.slice(0, 4);
export const longDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
export const multiple = (v: number | null | undefined) => (v == null ? "n/a" : `${v.toFixed(1)}×`);
export const pctOf = (v: number | null | undefined) => (v == null ? "n/a" : `${(v * 100).toFixed(1)}%`);

export type Bucket = { bucket: string; n: number; mean: number | null; median: number | null };
export type EvidenceTest = { lens: string; outcome: string; n: number; buckets: Bucket[]; spearman: number | null; p: number | null };
export type Evidence = {
  window: string; companies: number; horizon: string;
  all_quarters: { rows: number; tests: EvidenceTest[] };
  year_end_only: { rows: number; tests: EvidenceTest[] };
  held_out_year_end: { rows: number; tests: EvidenceTest[] };
};

export type NewsLine = { text: string; url: string; source: string; title: string; age: string | null };
export type NewsArticle = { title: string; url: string; source: string; age: string | null; text: string };
export type News = { retrieved: string; lines: NewsLine[]; articles: NewsArticle[] };

/** "2026-07-03" -> "Jul 2026" */
export const monthYear = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-GB", { month: "short", year: "numeric" });
/** Figures that are a snapshot on a date (balance sheet), not a twelve-month total. */
export const POINT_IN_TIME = new Set(["cash", "debt", "net_debt", "equity", "assets", "working_capital", "current_ratio"]);

export type QuickItem = { key: string; label: string; rule: string; result: "pass" | "partial" | "fail" | "unknown"; found: string };
export type QuickCheck = { applies: boolean; note?: string; items: QuickItem[]; score?: number | null; verdict?: string | null; source: string };

/** What the report is doing while it is built (the first lookup takes 20 to 30 seconds). Shown by the loading screen and the investor room. */
export const RESEARCH_STEPS = ["Finding the company's filings", "Reading the financial statements", "Reading the annual report for plans and R&D", "Reading the latest news and checking the share price"];
export const STEP_SECONDS = 4.5;

export type Decision = { call: "invest" | "wait" | "avoid"; label: string; why: string };
export type PanelTally = { counts: { invest: number; wait: number; avoid: number }; total: number; headline: string; tone: "good" | "watch" | "warn" };
export type Outlook = {
  odds: { years: number; history_years: number; chance_higher: number; chance_down_a_fifth: number; median_change: number;
          low_change: number; high_change: number; worst_year: number; best_year: number } | null;
  value_path: { name: string; start_growth: number; points: { year: number; value: number }[] }[];
  price: number | null; base_value_in_5y: number | null; return_if_price_meets_base: number | null;
  verdict: { tone: "good" | "watch" | "warn"; headline: string; why: string };
};
export const CALL_COLOR = { invest: "var(--green)", wait: "var(--amber)", avoid: "var(--red)" } as const;
