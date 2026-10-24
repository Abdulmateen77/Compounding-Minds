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
  market?: Market | null; plans?: Plans | null; notes?: string[]; missing?: string[]; analysis?: Analysis;
};
export type Check = { id: string; principle: string; source: string; check: string; result: "pass" | "partial" | "fail" | "unknown"; shown: string };
export type Lens = { key: string; name: string; question: string; fit: number | null; word: string; checks: Check[] };
export type Scenario = { name: string; start_growth: number; value_per_share: number | null; equity_value: number; fcf_path: number[]; revenue_path: number[] | null };
export type Valuation = {
  available: boolean; reason?: string; normalised_fcf?: number; discount_rate?: number; long_run_growth?: number; years?: number;
  scenarios?: Scenario[]; sensitivity?: { rate: number; values: (number | null)[] }[]; price?: number; implied_growth?: number | null;
  price_vs_base?: number | null; position?: string; position_text?: string;
};
export type Future = { scenarios: { name: string; start_growth: number; value_per_share: number | null; revenue: Record<string, number | null>; fcf: Record<string, number | null> }[] };
export type Overall = { key: string; tone: "good" | "watch" | "warn"; headline: string; why: string };
export type Analysis = { valuation: Valuation; lenses: Lens[]; overall: Overall; future: Future | null };
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
