# Demo script and judge Q&A

Written for: the team presenting at the hackathon (3 to 4 minutes live, then questions). Numbers marked **[replay]** come from the final replay and are filled in once it has finished and been read (see the bottom of this file).

## Before you go on stage
1. Start the app: `DASHBOARD_SOURCE=data/runs_final USE_STUBS=0 python -m uvicorn api.main:app --port 8000`, open http://localhost:8000.
2. **Warm the companies you will show.** The first lookup of a company takes 10 to 20 seconds (it reads the filings and asks the model for the written parts); after that it is instant for an hour. Open Tesla and Coca-Cola once before you start.
3. If the network or Yahoo is down, the report still builds (price and multiples are simply missing). Say so, and carry on.
4. Have the backup video ready. Record it from this script.

## The script (about 3 minutes 45 seconds)

**0:00 The problem (15 s).** "Every investor is told to read the annual report. Nobody reads fifty of them. So we built something that reads them for you, shows its working, and tells you how far to trust it."

**0:15 Type a company (20 s).** Type "Tesla". The dropdown says *Tesla, Inc., Nasdaq, United States.* Press Enter. "Any US-listed company. London and Europe are next."

**0:35 The verdict (25 s).** Top of the report: *Mixed evidence: some strengths, some doubts*, with six investor chips. "This reads the filings, not the news. Every number is computed in Python from the SEC filings. The AI only writes words."

**1:00 The numbers (30 s).** Scroll through growth, cash and the balance sheet. Hover a figure: it shows the SEC filing it came from. "Sales are up 8% over twelve months, but only 2.6% a year over three. Free cash flow is $3.3 billion, about 3% of sales, because capital spending jumped to 15% of sales."

**1:30 The company in its own words (20 s).** The quoted plans: "We currently expect our capital expenditures to be in excess of $20 billion in 2026." "These are copied word for word from its annual report, with a link. A model may only choose among sentences that exist; it cannot write one."

**1:50 How investors would read it (45 s).** Open the investor cards. Buffett: cash margin down while capital spending is up. Graham: the price assumes more than 45% growth a year, against 9.9% delivered. Lynch: names the kind of stock and compares the P/E with the growth rate. Munger: few ways to fail. Read one "Looking ahead" paragraph aloud. "Each view comes from the investor's own book and a checklist in our words. Every line cites its source."

**2:35 Does it work? (40 s).** Scroll to *Have these checks actually worked?* "We ran the same checks on 50 companies at every quarter from 2018 to 2023, using only the filings public at the time, and compared with what happened next. Munger's failure checks: companies passing few of them had a dividend cut or auditor change in **13%** of cases, against **2%** for those passing most. The right direction, but modest, and these events are rare. Buffett's quality checks: the companies that passed most kept a typical **14%** free-cash-flow margin a year later, against **4%** for those that passed few. And we say plainly what it does not show: the checks said nothing about sales growth, and we did not test whether prices rose."

**3:15 It checks itself, and learns (30 s).** Open *Past test*. "The original product: AI analysts make a call, Python grades it against the next filing, and every wrong call becomes a lesson the analyst reads next time. All model calls go through Mubit, which records them and trains small models on them. Mubit has no API for corrections, so our code puts the lesson in the next prompt, and we show the learned analyst beside an identical one that never learns." Show one wrong call, its lesson, and the same analyst re-asked. **[replay: name the example and the held-out result]**

**3:45 Close (15 s).** "Research, not advice. Every figure from the filings, every claim tested or labelled untested. Next: London and Europe."

## Judge Q&A

**Isn't this just ChatGPT with a prompt?**
No. Every figure is computed in Python from SEC filings and names its source. The model writes sentences under a guard that rejects any number the checks did not produce, and it can only quote sentences that exist in the annual report. And we tested the checks against what happened next.

**How do you stop it making things up?**
Three guards. Numbers come from code. A written paragraph is dropped if it uses a number that is not in the checks or the investor's guide. Quotes from the company are chosen by number from sentences already extracted from the filing, so the model cannot invent one.

**Does it predict the share price? Is this advice?**
No to both. It shows what the business could be worth under three stated growth cases, and what growth today's price already assumes. The overall reading describes the evidence and the price. The page says it is not personal advice.

**Why should I trust the valuation?**
You should not trust it blindly, and the page says so. It is a plain cash-flow calculation with the assumptions visible, the required return shown at 7%, 8% and 10%, and the reverse question "what does the price assume". At an 8% hurdle it often shows large companies as expensive; that is a property of the method, which is why it is shown as a range and not a target.

**Did the investor checks actually work?**
Two of the six were tested. Munger's failure checks point the right way but only modestly (13% of the weakest group had a dividend cut or auditor change within a year, against 2% of the strongest; rank correlation -0.13 over 1,184 company-quarters and the same with one window per company per year). On the 10 held-out companies there are too few cases to tell. We first got a much better-looking result (45% against 3%), found it was an artefact of how dividend timing was measured, fixed it, and report the smaller number. Buffett's quality checks predicted that cash margins persist, but not sales growth, and the cash check partly overlaps with what it predicts. Graham, Lynch, Dalio and Jhunjhunwala are not tested, because we hold no historical prices; the page labels them.

**Where does the investors' knowledge come from?**
Five books and one note: *The Warren Buffett Way*, *Poor Charlie's Almanack*, *The Intelligent Investor*, *One Up on Wall Street*, *Principles*, and a note on Rakesh Jhunjhunwala. We distilled each into a short guide in our own words, checked the key rules against the text (Graham's seven tests and thresholds, Lynch's six kinds and PEG rule, Munger's ten-point checklist, Dalio's expected-value rule). The Jhunjhunwala note is a summary of an interview and its figures are unverified, and the page says that.

**Where is Mubit in this?**
Every model call goes through Mubit's Anthropic-compatible proxy: the analysts, the lessons, and the written parts of the report. Mubit records each call and groups them into tasks per prompt. It has no API to take a correction, so we apply lessons in the prompt and keep the learned analyst beside a frozen twin. Mubit's own training makes small models from the recorded calls; we show that in its console, not from code.

**Is there look-ahead leakage?**
The date gate is in one place (`store/queries.py`): a fact is visible at a date only if its filing date is on or before it, with a test. The replay and the back-test both use it, so "what was known then" is what they see. In the live report the date is today.

**What about the UK and Europe? Banks?**
US-listed companies only for now; a search for anything else says so. Banks and insurers are covered partly: several measures (gross margin, EBITDA, debt to earnings) do not apply to them, and there is no valuation.

**Why are some figures marked approximate?**
Some companies never report operating income or a depreciation total. We estimate them (revenue minus total costs; depreciation alone) and mark them with an approximation sign and a note on the page. The grader's rule for the replay stays stricter.

**What did not work?**
The original replay analysts did not clearly beat a simple "always the common answer" baseline on the cash-and-margin question, because that outcome is rare. The research product does not depend on them: its checks are rules, tested directly. **[replay: add the held-out numbers]**

**What would you do with another week?**
Add UK and European listings through a market-data service; back-test the price checks once we have historical prices; read ownership and insider filings for the Jhunjhunwala checks; and fold the best of the new guide rules into the replay analysts' prompts in one deliberate change.

## Filling in the replay numbers (after the run finishes)
1. `python -m eval.run --from-replay data/runs_final --tag final` writes B's held-out report.
2. `python -m quality.cli --runs data/runs_final --out quality/out` writes the quality report with the base-rate baseline.
3. Read both against "always the most common outcome", not the always-yes baseline, and write what they say, including if the analysts do not win.
