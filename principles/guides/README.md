# Investor guides: the knowledge behind the report's investor lenses

Six short guides, each distilled in our own words from the source in `Documents/Personal Finance/Investors knowledge` (five books and one note). They are not the books and they quote nothing at length. Each has the same sections: the core idea, the questions the investor asks before investing, what they avoid, how they look ahead over the coming years, guidance for reading a stock through their eyes, machine-readable checks, and a source map to chapters.

| Guide | Source | Used for |
|---|---|---|
| `buffett.md` | *The Warren Buffett Way* (Hagstrom) | Quality, owner earnings, value, a ten-year hold |
| `munger.md` | *Poor Charlie's Almanack* | Inversion: how it could fail; psychology of misjudgment |
| `graham.md` | *The Intelligent Investor* | Margin of safety; the seven tests |
| `lynch.md` | *One Up on Wall Street* | Six kinds of stock; P/E against growth; the balance sheet |
| `dalio.md` | *Principles* | Probabilities, expected value, cycles, diversification |
| `jhunjhunwala.md` | your note (a summary of an interview; figures are unverified) | Growth, leadership, cash flow, return on capital |

## How they are used
- The report's investor lenses run the guides' checks against the company's own numbers (`research/analysis.py`).
- The paragraph under each lens ("what they would watch over the next few years") is written by a model that is given the guide and the checks, and nothing else. A number guard drops any paragraph that uses a figure that is not in the checks or the guide (`research/narrative.py`).

## Why these are separate from `principles/<investor>.md`
Those files are the replay agents' prompts. The replay (`--tag final`) ran on them as they are, and the demo replays from a cache keyed on the prompt, so editing them would make the demo run impossible to reproduce. The guides here feed the research product only. After the final replay is archived, the best of these rules can be folded into the agents' files in one deliberate change.

## Provenance and limits
- The books were read from the PDFs in the folder; page and chapter references are in each guide.
- Graham's thresholds are from 1972; Lynch's and Buffett's examples are from the 1980s and 1990s. They are habits of mind, not guarantees, and the report says so.
- The Jhunjhunwala note records the speaker's own claims and says so itself.
- Nothing here is investment advice.
