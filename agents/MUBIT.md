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
| Headers `x-middleware-store: false` and `x-middleware-record: metadata/off` stop a call being kept | Never set them on calls we want Mubit to train on |
| Training must be switched on for the workspace. Until then there is no Adapters page. Try models can also be off | Check the console before the demo |
| Daily training limit (resets 00:00 UTC), pause between trainings, 3 adapter starts per day in Try models | Send the training batch early, not on demo morning |
| Starter credit: only listed models (we use `claude-haiku-4-5`), body at most 8 MiB, only `POST /v1/messages`, `count_tokens` and `GET /v1/models` on Anthropic | `MubitGateway` default model |

## Still to ask Mubit (office hours)

1. Is training switched on for our workspace, and is Try models on?
2. Is there any way, even private or beta, to submit an outcome or correction for a call (an API,
   or the Good/Bad rating)? Does a `Bad` rating change kept examples or training?
3. Can a passing adapter serve live calls, and what does "Served by" show when it does?
4. Can we read a task's adapter version from code, to stamp it into `AgentCall.model`?
5. Would imported calls (Langfuse / Braintrust / Logfire import) with corrected answers become
   kept examples? That would be a real path from a correction to training data.
