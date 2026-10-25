# Mubit: what the docs say (read 24 Oct 2026)

Source: docs.mubit.ai, full text from `https://docs.mubit.ai/llms-full.txt`. A raw copy is in
`data/mubit_docs/` (gitignored). Refresh it with:

```bash
curl -sSL -o data/mubit_docs/llms-full.txt https://docs.mubit.ai/llms-full.txt
```

## The answer to "how does a correction become a model update?"

**There is no API for it.** The docs list no endpoint or header for feedback, outcomes,
ratings, labels, rewards or corrections, and none that starts a training run. Mubit's API is
only the provider proxy: `/anthropic`, `/openai/v1`, `/gemini` and `/compat/{service}/v1`.

How Mubit learns instead:
- It records every call and groups calls into **tasks**.
- It picks **kept examples** from a task. The first training runs at 25 kept examples.
- It trains an **adapter**, a small open model for that one task. Each training makes a new version.
- Each version is **tested against the provider model's answers**, not against ground truth.
  `Passed` means it answers close enough to the provider model.
- After that, a task trains a new version once enough new examples arrive ("Next: a new version
  after N new examples").
- There is no retrain button. Recovery is always "send more calls".

So Mubit distils the provider model into a cheaper adapter. It does not learn from outcomes.

## What that means for us

The honest chain for the demo:

1. A wrong call is graded by our Python grader.
2. Reflection writes a lesson.
3. The lesson goes into that agent's next prompts, in the user message, so the system prompt
   and therefore the Mubit task stay the same.
4. Those calls go through Mubit and become new kept examples **of the same task**.
5. Mubit trains the next adapter version on answers that already follow the lesson.

`MubitUpdater` does steps 3 and 4 and links each lesson to the Mubit request ID of the
reflection call that wrote it. Step 5 shows in the console (Tasks, Adapters, History); there
is no API to read it, so `get_model_version` is our own lesson counter, not a Mubit version.

## Facts our code relies on (all checked)

| Fact | Where we use it |
|---|---|
| A task is the same **instructions (system prompt), tools, tool choice, output format and model**. Messages after the instructions, `temperature` and `max_tokens` don't count | Everything that changes per call (company, metrics, lessons, tool instructions, rules) goes in the user message (`agents/runner.py`). Our tool use is a text protocol, **not** the API `tools` field, so it doesn't split tasks |
| Numbers, dates, times and IDs in the instructions don't split a task, but other changing words do | Same as above |
| The model ID is part of the task. Date suffixes and `-latest` are ignored | One model per agent task. A frontier-model arm is a separate task |
| On Anthropic, `metadata.user_id` is the session field | `MubitGateway` sends `session_id` there |
| Every answer carries `x-middleware-request-id` (`mreq_` + 32 hex digits) | Stored on each `MubitRequest` and on corrections |
| There is no Mubit model ID: you **can't** call an adapter by naming it as the model | We always call the provider model through Mubit |
| Adapters can only be tried in the console's **Try models** (side by side, not stored, trains nothing; limited starts per day) | Demo: show a passing adapter there, not from code |
| **Rate this reply: Good / Bad** exists on a call in the console's Requests page | Console only. The docs don't say ratings affect training |
| Headers `x-middleware-store: false` and `x-middleware-record: metadata/off` stop a call being kept | `complete(..., record=False)` sends `x-middleware-record: off` for calls that must not train or use the daily review budget: the held-out eval and the frozen control arm (`eval/harness.py`), the `envcheck` probe, and any test call. Analysts, reflection and the synthesizer stay recorded. Never set `x-middleware-store: false` or `x-middleware-record` on calls we want Mubit to train on. `agents/ledger.py` counts recorded calls per task (model + `system_sha`) per UTC day: `python -m agents.ledger` |
| Training must be switched on for the workspace. Until then there is no Adapters page. Try models can also be off | Check the console before the demo |
| Daily training limit (resets 00:00 UTC), pause between trainings, 3 adapter starts per day in Try models | Send the training batch early, not on demo morning |
| Starter credit: only listed models (we use `claude-haiku-4-5`), body at most 8 MiB, only `POST /v1/messages`, `count_tokens` and `GET /v1/models` on Anthropic | `MubitGateway` default model |

## Getting an adapter to pass (target 96%)

A version passes when it matches the provider model's answers often enough: `Matched {a}% of your provider
model's answers on {n} test cases · needs {need}%`. It is tested against the provider, not against reality, so
an adapter cannot match a provider that disagrees with itself. Two things on our side capped that:

1. **The provider varied its own reply.** The same analyst prompt sent twice gave a different probability,
   evidence list and principles list most of the time. `temperature` can't fix it: Mubit's Anthropic route
   rejects it (`temperature: Extra inputs are not permitted`). So `agents/runner.py` adds `FORMAT_RULES` to the
   USER message (the task key is unchanged): two probability levels, every metric as evidence, every principle
   id listed, three bullets, bare JSON, and the format rules win over a lesson about the reply's shape.
   Scenarios also gets dalio.04 as its default (start from the bucket of the 5-year mean).
2. **One session per task.** Mubit sets test cases aside by session. The narrative, chat and news calls sent
   one fixed session per task, which left nothing to test on. They now send one session per company.

`python -m agents.agreement` measures the provider against itself (each prompt twice, `record=False`, so it
trains nothing). Real prompts, Haiku 4.5, 25 Oct 2026:

| | before (no rules, no lessons, 15 pairs) | after (rules + learned lessons, 40 pairs) |
|---|---|---|
| fundamentals | 33% | 98% |
| risk | 47% | 95% |
| scenarios | 33% | 95% |

A pair "matches" on the same answer, probabilities within 0.05, the same evidence set and principles overlapping
at least 0.75; reasoning wording is reported but does not count. This is our own proxy, not Mubit's test.
It bounds what an adapter can reach; it does not show that a small adapter will reach it.

Training set: `python -m agents.mubit_batch --source real` sends real prompts from the store, training
companies only, with the learned lessons, as recorded calls. The pass result itself is only in the console
(Adapters > History); there is no API to read it.

## One call that does not go through the gateway

`grader/sapling.py` posts going-concern passages straight to Mubit's Banyan Sapling verifier endpoint (it is a verifier, not a chat model, and has its own interface). Verdicts are cached, so a replay makes no live calls. Every chat-model call in the repo goes through `MubitGateway`.

## Still to ask Mubit (office hours): unanswered at submission

We did not get answers to these before the deadline, so nothing in the app depends on them.

1. Is training switched on for our workspace, and is Try models on?
2. Is there any way, even private or beta, to submit an outcome or correction for a call (an API,
   or the Good/Bad rating)? Does a `Bad` rating change kept examples or training?
3. Can a passing adapter serve live calls, and what does "Served by" show when it does?
4. Can we read a task's adapter version from code, to stamp it into `AgentCall.model`?
5. Would imported calls (Langfuse / Braintrust / Logfire import) with corrected answers become
   kept examples? That would be a real path from a correction to training data.
