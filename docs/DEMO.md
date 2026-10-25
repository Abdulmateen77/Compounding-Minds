# Demo script and judge Q&A

The 2-minute video is the main thing judges see, so the script below is timed to **110 seconds**, about 270 spoken words at an easy
pace. The longer version (3 to 4 minutes live) is in the Q&A section's source, the product tour, if you present in person.

## Before you record
1. Start the app: `make demo` (needs Python 3.11+ and Node 20+; it serves http://localhost:8000). The Track record tab reads the
   committed replay in `demo_data/runs_final`, so it needs no keys.
2. For the Research part, put `SEC_USER_AGENT`, `MUBIT_API_KEY` and `MUBIT_BASE_URL` in `.env`. **Warm the company you will show**:
   the first lookup takes 10 to 20 seconds (it reads the filings and asks the model for the written parts), then it is instant for an hour.
   Open Tesla (or Coca-Cola) once before you record.
3. If the network or Yahoo is down, the report still builds (price and multiples are simply missing). Say so, and carry on.
4. Record the screen at 1080p, with the browser window at about 1440 wide, one take per section, and cut them together. Put the link in the README (`VIDEO_LINK_HERE`).

## The script (110 seconds)

**0:00 The problem (10 s).** *Screen: the landing page.* "Nobody reads fifty annual reports. This reads them for you, shows its working, and checks itself against what really happened."

**0:10 Type a company (10 s).** *Type "Tesla", press Enter.* "Any US-listed company. It reads the filings."

**0:20 Numbers you can trace (15 s).** *The verdict and chips, then hover one figure so the SEC filing shows.* "Every figure is computed in Python and names the filing it came from. The AI only writes words, and a guard drops any sentence with a number the checks did not produce."

**0:35 The company in its own words (10 s).** *Scroll to the quoted plans.* "These plans are copied word for word from the annual report, with a link. A model can only choose among sentences that exist."

**0:45 Five investors read the same facts (15 s).** *Open the Investors tab; click Buffett, then the price-assumption line.* "Buffett, Munger, Lynch, Jhunjhunwala and Dalio read the same figures as rule checks from our own written guides, each with a source. The valuation shows what growth today's price already assumes. Research, not advice: no price target."

**1:00 Do the checks work? (15 s).** *Scroll to the back-test box.* "We ran the checks on 50 companies at every quarter from 2018 to 2023, using only filings public at the time. Companies passing few of Munger's failure checks had a dividend cut or auditor change in 13% of cases, against 2% for those passing most. Right direction, but modest."

**1:15 It grades its own analysts, and Mubit (25 s).** *Open Track record, pick Fundamentals, show the latest lesson, then the learned and frozen lines.* "AI analysts make calls from 2018 to 2024, seeing only what was public then. Python grades each against the next filing. Every wrong call becomes a lesson that goes into that analyst's next prompt. All model calls go through Mubit, which records them. An identical frozen twin never gets lessons."

**1:40 The honest result (10 s).** *Show the held-out numbers on the Track record page.* "On years and companies it never saw, the learned analyst did not beat its twin: 58% against 60% on cash margins, 58% against 64% on revenue. We report that, because a result you can't lose isn't a test."

**1:50 Close.** "Research, not advice."

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
Learning did not help in the replay. On the held-out window (2023-2024) the learned analyst scored 58.0% against its frozen twin's 60.0% on the cash-margin question (the base rate alone is 60.0%), and 57.9% against 63.8% on the revenue-bucket question; Brier scores were level and worse respectively. The Risk analyst's stored grades predate a grading fix, so we do not quote its accuracy. The research product does not depend on the analysts: its checks are rules, tested directly.

**What would you do with another week?**
Add UK and European listings through a market-data service; back-test the price checks once we have historical prices; read ownership and insider filings for the Jhunjhunwala checks; and fold the best of the new guide rules into the replay analysts' prompts in one deliberate change.

## Where the replay numbers come from
1. `python -m eval.run --from-replay demo_data/runs_final --tag final --agents fundamentals,scenarios` writes the held-out report (`eval/reports/heldout_report.md`), with no model calls.
2. Read it against the base rate as well as the always-yes baseline, and write what it says, including when the analysts do not win.
