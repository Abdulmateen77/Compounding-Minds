import { LEVEL_KEYS, setPrefs, usePrefs, type Level } from "./prefs";

/* Financial literacy. A six-question quiz sets one of three levels; the level is kept in this browser (prefs.ts) and read by
   every part of the site: definitions on jargon (components/Say.tsx), the guide strips and the "what this means" lines, the debate,
   the voices and the investor chat. Nothing here changes a number; it only changes how much explaining goes around the numbers. */

export type { Level };
export { LEVEL_KEYS };

export const LEVELS: Record<Level, { name: string; short: string; changes: string[] }> = {
  beginner: {
    name: "Beginner",
    short: "New to investing: plain words, every term explained.",
    changes: ["Finance terms are underlined: tap one for a plain definition.", "A short guide opens each page and each section.", "The investors answer in everyday words, with comparisons."],
  },
  intermediate: {
    name: "Intermediate",
    short: "Knows the basics: only the specialist terms explained.",
    changes: ["Only the specialist terms (such as DCF and return on capital) are explained.", "Short “what this means” lines stay under each figure.", "The investors explain the less common terms as they go."],
  },
  advanced: {
    name: "Advanced",
    short: "Fluent: no definitions, more detail and sources.",
    changes: ["No definitions or guide strips: the figures and checks stand alone.", "Each figure shows the filing it came from instead of an explanation.", "The investors use the precise terms and keep it short."],
  },
};

export const useLevel = (): Level | null => usePrefs().level;
/** The level to write for: the reader's, or the middle one until they have chosen. */
export const useEffectiveLevel = (): Level => useLevel() ?? "intermediate";
export const setLevel = (level: Level) => setPrefs({ level });

/* ───────────────────────── the quiz ───────────────────────── */

export type Question = { q: string; options: string[]; answer: number };

/** Easy to hard. The quiz adds an "I'm not sure" option to each; a wrong guess and "not sure" score the same, so there is no reason to guess. */
export const QUIZ: Question[] = [
  { q: "A company reports revenue of $10 billion for the year. What is revenue?",
    options: ["The money it took in from sales, before any costs", "The profit left after all costs and tax", "The cash in its bank account", "The value of everything it owns"], answer: 0 },
  { q: "A company's profit is up, but its free cash flow fell. What does free cash flow measure?",
    options: ["Total sales for the year", "Cash left after running the business and paying for equipment and buildings", "The dividend paid to shareholders", "The company's share price rise"], answer: 1 },
  { q: "A stock has a P/E ratio of 25. What does that tell you?",
    options: ["The price is 25 times a year of its profit per share", "It will grow 25% a year", "25% of its shares are owned by insiders", "It pays a 25% dividend"], answer: 0 },
  { q: "Investors say a business has a “wide moat”. What do they mean?",
    options: ["It holds a lot of cash", "It has a lasting advantage that keeps competitors from taking its customers", "It is in a very safe industry", "Its debt is small"], answer: 1 },
  { q: "A company's net debt is 4 times its EBITDA, up from 1 time two years ago. What is the likely worry?",
    options: ["It is hoarding cash", "Its earnings are rising too quickly", "It is borrowing much more than it earns, so a bad year could be hard to survive", "Its shares have become cheaper"], answer: 2 },
  { q: "In a discounted cash flow (DCF) valuation, what happens to the estimated value if you raise the discount rate and change nothing else?",
    options: ["It falls, because future cash is worth less today", "It rises, because the risk is rewarded", "It stays the same", "It depends on the share price"], answer: 0 },
];

/** 0 to 2 right: beginner. 3 to 4: intermediate. 5 to 6: advanced. */
export const levelForScore = (score: number): Level => (score >= 5 ? "advanced" : score >= 3 ? "intermediate" : "beginner");

/* ───────────────────────── the glossary ───────────────────────── */

/** `hard`: explained for beginners and intermediates; otherwise for beginners only. `spoken` is how a voice should say it. */
type Entry = { id: string; term: string; match: string; def: string; hard?: boolean; spoken?: string };

const E = (id: string, term: string, match: string, def: string, hard = false, spoken?: string): Entry => ({ id, term, match, def, hard, spoken });

export const GLOSSARY: Entry[] = [
  E("revenue", "Revenue", "revenue|sales", "The money a company takes in from customers, before any costs come off."),
  E("gross-margin", "Gross margin", "gross margin", "What is left of each dollar of sales after the direct cost of making the product."),
  E("operating-margin", "Operating margin", "operating margin", "Profit from the core business for each dollar of sales, before interest and tax."),
  E("margin", "Margin", "profit margin|margins?", "Profit as a share of sales. A 20% margin means 20 cents kept from each dollar sold."),
  E("net-income", "Net income", "net income|net profit|earnings", "What is left after every cost, interest and tax: the bottom line."),
  E("fcf", "Free cash flow", "free[- ]cash(?:[- ]flow)?|FCF", "Cash left over after running the business and paying for equipment and buildings. Cash that could be paid out or saved.", false, "free cash flow"),
  E("cash-flow", "Cash flow", "cash flows?", "Money actually moving in and out of the business, which can differ from reported profit."),
  E("capex", "Capital spending (capex)", "capex|capital spending|capital expenditure", "Spending on things that last, such as factories, machines and buildings.", false, "capital spending"),
  E("rnd", "R&D", "R&D|research and development", "Money spent inventing new products and improving old ones.", false, "research and development"),
  E("dividend", "Dividend", "dividends?", "A share of profit paid out to shareholders, usually every quarter."),
  E("dividend-yield", "Dividend yield", "dividend yield", "The yearly dividend as a percentage of the share price.", false),
  E("buyback", "Share buyback", "buybacks?|share repurchases?", "The company buys its own shares back, so each remaining share is a bigger slice."),
  E("market-cap", "Market cap", "market cap(?:italisation|italization)?", "The price of one share times all the shares: what the stock market says the whole company is worth."),
  E("debt", "Debt", "debt|borrowings", "Money the company has borrowed and must repay with interest."),
  E("balance-sheet", "Balance sheet", "balance sheet", "A snapshot of what a company owns and owes on one day."),
  E("equity", "Equity", "shareholders'? equity|equity", "What would be left for shareholders if everything owned were sold and every debt paid."),
  E("tenk", "10-K", "10-K", "The annual report a US-listed company files with the SEC.", false, "ten-K"),
  E("tenq", "10-Q", "10-Q", "The quarterly report a US-listed company files with the SEC.", false, "ten-Q"),
  E("eightk", "8-K", "8-K", "A short notice a company must file when something important happens.", false, "eight-K"),
  E("sec", "SEC", "SEC", "The US regulator that requires listed companies to publish their accounts."),
  E("valuation", "Valuation", "valuation", "An estimate of what a business is worth, to compare with its price."),
  E("pts", "Percentage points", "pts|percentage points?|ppts?", "The gap between two percentages: going from 10% to 12% is up 2 percentage points.", false, "percentage points"),
  E("scenarios", "Bull, base and bear", "bull case|base case|bear case", "Three stories for the future: a good one (bull), a middling one (base) and a bad one (bear)."),
  E("going-concern", "Going concern", "going[- ]concern", "An auditor's warning that the company may not survive the next twelve months."),
  E("yield-curve", "Yield curve", "yield curve", "The gap between long and short government interest rates. When short rates are higher, a slowdown often follows."),
  E("credit-spread", "Credit spread", "credit spread", "The extra interest companies pay to borrow compared with the government. It widens when lenders get nervous."),
  E("gdp", "GDP", "GDP", "The total value of everything a country produces in a year: the size of its economy."),

  E("roic", "Return on invested capital (ROIC)", "ROIC|return on (?:invested )?capital", "How much profit the business earns for every dollar put into it. Higher means it uses money well.", true, "return on invested capital"),
  E("roe", "Return on equity (ROE)", "ROE|return on equity", "Profit as a share of the shareholders' stake. High numbers can come from debt, so check that too.", true, "return on equity"),
  E("ebitda", "EBITDA", "EBITDA", "Earnings before interest, tax, depreciation and amortisation: a rough measure of operating profit.", true),
  E("ev", "Enterprise value", "enterprise value", "The price of the whole business: market cap plus debt, minus cash.", true, "enterprise value"),
  E("ev-ebitda", "EV/EBITDA", "EV/EBITDA|EV to EBITDA", "Enterprise value divided by EBITDA: how many years of operating earnings it would take to pay for the whole business.", true, "enterprise value to EBITDA"),
  E("pe", "P/E ratio", "P/E|price[- ]to[- ]earnings|PE ratio", "Share price divided by a year of profit per share: how many dollars you pay for each dollar of yearly profit.", true, "price to earnings"),
  E("ps", "Price-to-sales", "P/S|price[- ]to[- ]sales", "Market value divided by a year of sales.", true, "price to sales"),
  E("fcf-yield", "Free-cash-flow yield", "FCF yield|free[- ]cash[- ]flow yield", "A year of free cash flow as a percentage of the price. The cash return you would get if you owned the whole business.", true, "free cash flow yield"),
  E("dcf", "Discounted cash flow (DCF)", "DCF|discounted cash[- ]flow", "A way to value a business by adding up the cash it should earn in future, each year counted for less because later money is worth less than money today.", true, "discounted cash flow"),
  E("discount-rate", "Discount rate", "discount rate|required return", "The yearly return you demand to wait for future cash. A higher rate makes future cash worth less today.", true),
  E("intrinsic", "Intrinsic value", "intrinsic value", "What a business is really worth from the cash it can produce, whatever the market price says.", true),
  E("mos", "Margin of safety", "margin of safety", "Buying well below your estimate of value so that you are still fine if you are somewhat wrong.", true),
  E("moat", "Moat", "(?:wide |narrow )?moat", "A lasting advantage, such as a strong brand or low costs, that protects a business from competitors.", true),
  E("leverage", "Leverage", "leverage|leveraged", "Using borrowed money. It boosts gains in good years and losses in bad ones.", true),
  E("debt-ebitda", "Debt to EBITDA", "debt[- ]to[- ]EBITDA|debt vs earnings|net debt to EBITDA", "Years of operating earnings needed to repay the debt. Under 2 is comfortable; over 4 is heavy.", true),
  E("net-debt", "Net debt", "net debt", "Debt minus cash: what would still be owed if all the cash were used to pay it down.", true),
  E("interest-cover", "Interest cover", "interest cover(?:age)?", "How many times operating profit covers the interest bill. Under 2 is thin.", true),
  E("current-ratio", "Current ratio", "current ratio|short-term cushion", "Short-term assets divided by bills due within a year. Above 1 means it can pay them.", true),
  E("working-capital", "Working capital", "working capital", "Short-term assets minus short-term bills: the money tied up in running day to day.", true),
  E("book", "Book value", "book value|price[- ]to[- ]book", "What the accounts say the company is worth: its assets minus its debts.", true),
  E("terminal", "Long-run growth", "long-run growth|terminal growth|terminal value", "The steady growth rate assumed forever after the forecast years. Small changes here move a valuation a lot.", true),
  E("normalised", "Normalised", "normali[sz]ed", "Smoothed over several years so that one unusually good or bad year does not mislead.", true),
  E("sensitivity", "Sensitivity table", "sensitivity", "Shows how the answer changes if an assumption is a bit different.", true),
  E("cagr", "Compound growth (CAGR)", "CAGR|compound annual growth", "The steady yearly growth rate that would turn the starting figure into the ending one.", true, "compound annual growth rate"),
  E("bps", "Basis points", "basis points?|bps", "One hundredth of a percentage point. 50 basis points is half a percent.", true, "basis points"),
  E("median", "Median", "median", "The middle result when all are lined up in order, so one extreme does not skew it.", true),
  E("drawdown", "Drawdown", "drawdown|down a fifth", "A fall from a peak to a low point.", true),
  E("beta", "Sensitivity to the economy", "sensitivity to the economy|macro beta", "How closely sales have moved with the whole economy. Above 1 means it swings more than the economy does.", true),
  E("treasuries", "Treasuries", "Treasur(?:y|ies)", "Bonds issued by the US government, treated as the safest place to lend.", true),
  E("brier", "Brier score", "Brier score", "A score for forecasts that stated a confidence. Lower is better; always saying 50-50 scores 0.25.", true),
  E("calibration", "Calibration", "calibrat(?:ion|ed)", "Whether “70% sure” turns out right about 70 times in 100.", true),
  E("backtest", "Back-test", "back-?tested?|back-?testing", "Running a method on past years, using only what was known then, to see how it would have done.", true),
  E("heldout", "Held-out test", "held[- ]out", "A test on companies the method never saw while it was being tuned, to catch over-fitting.", true),
  E("spearman", "Rank correlation", "spearman|rank correlation", "How well a ranking matches the real ranking. 1 is perfect, 0 is no better than chance.", true),
];

type Seg = string | { id: string; term: string; def: string };

const compiled = GLOSSARY.map((e) => ({ e, re: new RegExp(`(?<![A-Za-z0-9/-])(?:${e.match})(?![A-Za-z0-9/])`, "gi") }));

/** Split `text` into plain strings and glossary terms. Beginners get every entry, intermediates the specialist ones, advanced readers none.
    Each term is marked once per call (the first mention), and a longer term wins over a shorter one that overlaps it. */
export function glossify(text: string, level: Level): Seg[] {
  if (level === "advanced" || !text) return [text];
  const hits: { start: number; end: number; e: Entry }[] = [];
  for (const { e, re } of compiled) {
    if (level === "intermediate" && !e.hard) continue;
    for (const m of text.matchAll(re)) hits.push({ start: m.index!, end: m.index! + m[0].length, e });
  }
  hits.sort((a, b) => a.start - b.start || b.end - b.start - (a.end - a.start));
  const seen = new Set<string>(), out: Seg[] = [];
  let at = 0;
  for (const h of hits) {
    if (h.start < at) continue;                       // overlaps a term already placed (the longer one came first)
    if (seen.has(h.e.id)) continue;                   // only the first mention of a term is marked
    seen.add(h.e.id);
    if (h.start > at) out.push(text.slice(at, h.start));
    out.push({ id: h.e.id, term: text.slice(h.start, h.end), def: `${h.e.term}: ${h.e.def}` });
    at = h.end;
  }
  if (at < text.length) out.push(text.slice(at));
  return out;
}

/** Text for a voice: abbreviations said the way a person says them. Advanced readers hear the text as written. */
export function spokenForm(text: string, level: Level): string {
  if (level === "advanced") return text;
  let out = text;
  for (const { e, re } of compiled) {
    if (!e.spoken) continue;
    out = out.replace(re, e.spoken);
  }
  return out;
}

/** What the investor chat is told about the reader (sent with each question; the server turns it into a style note). */
export const chatLevel = (l: Level) => l;
