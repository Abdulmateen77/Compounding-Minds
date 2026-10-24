# Principle sources: verification status

The principle files are in our own words, with a citation per rule. Checked on Sat 24 Oct 2026 against the
original texts where they are public (berkshirehathaway.com letters and owner's manual, transcripts of
Munger's talks, principles.com and economicprinciples.org). Only short phrases are quoted below, as evidence
that the idea is in the source.

**The rule files themselves were not edited.** Each file is sent whole as the agent's system prompt, and the
final replay (`--tag final`) ran with them as they are. Editing them would change every prompt, invalidate the
reply cache the demo replays from, and make the run unreproducible. Where a file's citation is loose or
wrong, the column "Correct citation" below is the one to use in the demo, the README and any Q&A.

| Rule ids | Citation in the file | Correct citation (verified) | Evidence in the source | Status |
|---|---|---|---|---|
| buffett.01 | Berkshire letters, "owner earnings" (1986 letter) | 1986 letter, Appendix "Purchase-Price Accounting Adjustments and the 'Cash Flow' Fallacy" | defines owner earnings as reported earnings plus non-cash charges, less the capex the business requires "to fully maintain its long-term competitive position and its unit volume" | [x] |
| buffett.02 | Berkshire letters, owner's manual tenets | Acquisition criteria printed in the letters (e.g. 2014 letter), item 3 | "Businesses earning good returns on equity while employing little or no debt" | [x] corrected: not the owner's manual |
| buffett.03 | Berkshire letters, maintenance vs growth capex | 1986 letter, same appendix as buffett.01 | maintenance capex is subtracted to get owner earnings | [x] |
| buffett.04 | Berkshire letters, "consistent earning power" | Acquisition criteria (e.g. 2014 letter), item 2 | "Demonstrated consistent earning power (future projections are of no interest to us ...)" | [x] |
| buffett.05 | Berkshire letters, on borrowing and staying power | Owner's Manual, principle 7 | "We use debt sparingly"; "We will reject interesting opportunities rather than over-leverage our balance sheet" | [x] |
| buffett.06 | derived rule (buffett.01 + .03) | same | n/a | n/a |
| munger.01 | Almanack, "A Lesson on Elementary Worldly Wisdom" (inversion) | Harvard School commencement, 13 June 1986 ("How to Guarantee a Life of Misery"), reprinted in Poor Charlie's Almanack | Jacobi's "Invert, always invert". The 1994 USC talk does **not** mention inversion | [x] corrected |
| munger.02 | Almanack, on avoiding obvious ways to fail | Harvard School commencement, 1986 (the whole speech inverts: list the ways to fail, then avoid them) | inversion applied to failure | [x] the source is the idea; the coverage threshold is ours |
| munger.03 | Almanack, on avoiding stupidity over seeking brilliance | Wesco Financial 1989 annual report, Munger's letter of 5 March 1990 (traced by Quote Investigator) | "trying to be consistently not stupid, instead of trying to be very intelligent" | [x] corrected: a Wesco letter, quoted in the Almanack |
| munger.04, .05 | derived rules | same | n/a | n/a |
| munger.06 | Almanack, on staying within what you can judge | "A Lesson on Elementary Worldly Wisdom", USC Business School, 1994 | "Every person is going to have a circle of competence"; "figure out where you've got an edge" | [x] |
| dalio.01, .05 | Principles, decision-making | Principles (2017), decisions as bets weighed by probability and reward (expected value) | principles.com: every decision as a bet with a probability of being right and a reward, and of being wrong and a penalty | [x] the idea; "calibrated confidence vs growth std" is our operationalisation |
| dalio.04 | Principles, cause-and-effect patterns | Principles (2017), the economy and life as machines of cause and effect | not checked word for word against the book | [~] plausible, unchecked text |
| dalio.02, .03 | "How the Economic Machine Works" (credit cycle) | "How the Economic Machine Works" (2013), credit, interest rates, leveraging and deleveraging cycles | the piece is about credit and debt cycles; it does **not** mention the yield curve or credit spreads | [x] the idea; the yield-curve and BAA-spread checks are our operationalisation |
| graham.01 to .06 | The Intelligent Investor, ch. 11, 14, 20 | stretch agent, not in the MVP replay | not checked | [ ] |
| moat.01 | Berkshire letters, "economic castle" (1995 and 2007) | 1995 letter; 2007 letter | 1995: "economic castles protected by unbreachable 'moats'"; 2007: "an enduring 'moat' that protects excellent returns on invested capital" | [x] (stretch agent) |
| moat.02 to .06 | FCIC interview / letters / derived | stretch agent | not checked | [ ] |

How to say it in the demo: "Each rule is our own wording, and every one used in the replay points to a source
we checked: the Berkshire letters, Munger's talks and Wesco letters, and Dalio's writing. Where a check like
'inverted yield curve' is ours rather than the investor's, we say so."

## Rules for editing a principles file
1. One rule per line: `id | rule | how to check with metrics | source`. The id pattern `name.NN` is parsed by
   `agents/reflection.py`, so keep it.
2. 5 to 10 rules per investor. No long quotes.
3. The "how to check" column may only name metrics the investor's agent is actually given. A test
   (`agents/tests/test_principles_contract.py`) enforces this, because an agent that cites a metric it was
   never shown fails the evidence check.
4. Editing a file changes the agent's system prompt: every cached reply for that agent is invalidated, so the
   replay must be re-run live. Do not edit after the final run.
