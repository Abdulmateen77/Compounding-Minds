# Replay cost and time estimate

Inputs: 50 companies x 3 agents x 28 quarters, 2 LLM arms (learned, frozen; baseline is free).

- analyst calls: 8,820  (incl. 5% repair retries, 0.0 tool calls/call)
- reflection calls: 600  (45% wrong, train window only, cap 10 per agent-quarter)
- total calls: 9,420
- tokens: 7.7M in, 3.2M out (prompt measured at 719 tokens, chars/3.6)

| model | $/MTok in | $/MTok out | total USD |
|---|---|---|---|
| claude-haiku-4-5 | 1.00 | 5.00 | $23.78 |
| claude-haiku-5-5 | 0.10 | 0.50 | $2.38 |
| claude-sonnet-5-5 | 2.00 | 10.00 | $47.57 |
| claude-opus-5-5 | 4.00 | 20.00 | $95.14 |

| concurrency | wall time at 50 RPM, 4s/call |
|---|---|
| 1 | 10.5 h |
| 4 | 3.1 h |
| 8 | 3.1 h |
| 16 | 3.1 h |

Notes: prices from the Claude API skill table (cached 2026-10-06). Mubit's own fees are not included. `temperature` is rejected by the API from 2026-10-21, so determinism comes from the reply cache (prompt hash + model version): a second run is free. Run the demo from cache with `--replay-only`. Full replay is sequential today; the 1-concurrency row is what it will take.
