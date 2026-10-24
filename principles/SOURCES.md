# Principle sources: verification status

The principle files are in our own words, with a citation per rule. The citations were written from
memory of the source material and are **not yet checked against the books and letters**. Before the
demo, every row below must be ticked by reading the source. Do not quote long passages; a rule only
needs to point at where the idea comes from. If a citation cannot be confirmed, change it to
"derived rule, our own synthesis of <ids>" (as `buffett.06` and `munger.04` already do).

How to check quickly: the Berkshire shareholder letters are public (berkshirehathaway.com). Firecrawl
can scrape a letter to markdown so you can search it for the phrase.

| Rule ids | Cited source | Verified |
|---|---|---|
| buffett.01 | Berkshire letters, "owner earnings" (1986 letter, appendix on goodwill) | [ ] |
| buffett.02, .04 | Berkshire letters, owner's manual tenets | [ ] |
| buffett.03 | Berkshire letters, maintenance vs growth capex | [ ] |
| buffett.05 | Berkshire letters, borrowing and staying power | [ ] |
| buffett.06 | Derived from buffett.01 and .03 | n/a |
| munger.01, .02, .03, .06 | Poor Charlie's Almanack: "A Lesson on Elementary Worldly Wisdom" (inversion, avoiding stupidity) | [ ] |
| munger.04, .05 | Derived rules, to be checked on the training window | n/a |
| dalio.01, .04, .05 | Principles (Dalio), decision-making sections | [ ] |
| dalio.02, .03 | "How the Economic Machine Works" (credit cycle) | [ ] |
| graham.01 to .06 | The Intelligent Investor: ch. 11, 14, 20 | [ ] |

## Rules for editing a principles file
1. One rule per line: `id | rule | how to check with metrics | source`. The id pattern `name.NN` is parsed by
   `agents/reflection.py`, so keep it.
2. 5 to 10 rules per investor. No long quotes.
3. The "how to check" column may only name metrics the investor's agent is actually given. A test
   (`agents/tests/test_principles_contract.py`) enforces this, because an agent that cites a metric it was
   never shown fails the evidence check.
