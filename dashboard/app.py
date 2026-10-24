"""Compounding Minds replay dashboard (README 11).

    streamlit run dashboard/app.py                         # Postgres if reachable, else data/runs
    DASHBOARD_SOURCE=data/runs streamlit run dashboard/app.py
    streamlit run dashboard/app.py -- --source data/runs_final   # the real replay, even while it runs

Reads stored runs only. No live API calls, no LLM calls. A JSONL source is re-read whenever its files
change, so a replay that is still writing shows its finished quarters and flags the partial one.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from dashboard import data as D  # noqa: E402

load_dotenv(ROOT / ".env")
st.set_page_config(page_title="Compounding Minds", page_icon="📈", layout="wide")

LEARNED, FROZEN, FRONTIER, BASELINE = "#2563eb", "#9ca3af", "#a855f7", "#f59e0b"
GOOD, BAD = "#16a34a", "#dc2626"
ARM_COLOR = {"learned": LEARNED, "frozen": FROZEN, "frontier": FRONTIER, "baseline": BASELINE}
CURVE_ARMS = ("learned", "frozen", "frontier", "baseline")

# `streamlit run dashboard/app.py -- --source data/runs_final` (Streamlit passes args after `--`).
_cli = argparse.ArgumentParser(add_help=False)
_cli.add_argument("--source")
_args, _ = _cli.parse_known_args(sys.argv[1:])
if _args.source:
    os.environ["DASHBOARD_SOURCE"] = _args.source

st.markdown("""
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 4rem;}
.cm-banner {padding: .6rem .9rem; border-radius: .5rem; margin-bottom: .6rem; font-size: .92rem;}
.cm-warn {background: rgba(234,179,8,.15); border: 1px solid rgba(234,179,8,.5);}
.cm-info {background: rgba(37,99,235,.10); border: 1px solid rgba(37,99,235,.35);}
.cm-step {border: 1px solid rgba(128,128,128,.3); border-radius: .6rem; padding: .8rem 1rem; height: 100%;}
.cm-step h4 {margin: 0 0 .35rem 0; font-size: .8rem; text-transform: uppercase; letter-spacing: .06em; opacity: .7;}
.cm-pill {display: inline-block; padding: .05rem .5rem; border-radius: 999px; font-size: .8rem; font-weight: 600;}
.cm-ok {background: rgba(22,163,74,.15); color: #16a34a;}
.cm-bad {background: rgba(220,38,38,.15); color: #dc2626;}
.cm-neutral {background: rgba(128,128,128,.18);}
.cm-footer {position: fixed; bottom: 0; left: 0; right: 0; text-align: center; padding: .35rem;
            font-size: .8rem; background: rgba(128,128,128,.14); backdrop-filter: blur(8px);
            border-top: 1px solid rgba(128,128,128,.25); z-index: 1000;}
</style>
""", unsafe_allow_html=True)
# Rendered before anything can st.stop(), so every view (empty, error, normal) carries it.
st.markdown('<div class="cm-footer">Research tool, not financial advice. Replay of cached runs; '
            'no live market data.</div>', unsafe_allow_html=True)


# ---- data --------------------------------------------------------------------

@st.cache_data(show_spinner="Loading stored runs…", max_entries=2)
def _load(source: str, stamp: float) -> D.Bundle:  # stamp: files' mtime, so new replay rows reload
    return D.load(source)


source = D.resolve_source()
try:
    bundle = _load(source, D.source_stamp(source))
except Exception as e:  # noqa: BLE001
    st.title("Compounding Minds")
    st.error(f"Could not read runs from `{source}`: {e}")
    st.caption("Check `DATABASE_URL` / `DASHBOARD_SOURCE`, or regenerate with "
               "`python -m eval.run --save data/runs`, then reload.")
    st.stop()

if bundle.empty:
    st.title("Compounding Minds")
    st.info("No stored runs yet. Generate an offline preview with:\n\n"
            "`python -m eval.run --agents fundamentals,risk,scenarios,valuation,moat --curves --save data/runs`")
    st.stop()

QUARTERS = D.quarters(bundle)
CTABLE = D.company_table(bundle)
AGENTS = [a for a in D.AGENTS if a in set(bundle.calls["agent"])]


def qlabel(d) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def pill(text: str, kind: str) -> str:
    return f'<span class="cm-pill cm-{kind}">{text}</span>'


def outcome_pill(correct) -> str:
    if correct is None or pd.isna(correct):
        return pill("unresolved", "neutral")
    return pill("correct", "ok") if bool(correct) else pill("wrong", "bad")


def pct(x) -> str:
    return "–" if x is None or pd.isna(x) else f"{x:.0%}"


def num(x, fmt=".3f") -> str:
    return "–" if x is None or pd.isna(x) else format(x, fmt)


# ---- sidebar: replay timeline ---------------------------------------------------

if "q_idx" not in st.session_state:
    st.session_state.q_idx = len(QUARTERS) - 1
# A replay still writing (or a reload mid-rewrite) can change the number of quarters between reruns.
st.session_state.q_idx = max(0, min(st.session_state.q_idx, len(QUARTERS) - 1))
if "playing" not in st.session_state:
    st.session_state.playing = False
# The play loop asks for the next quarter here, before the slider exists: Streamlit forbids
# changing a widget's state after the widget has been drawn in the same run.
if st.session_state.pop("_advance", False):
    st.session_state.q_idx = min(st.session_state.q_idx + 1, len(QUARTERS) - 1)

with st.sidebar:
    st.header("Time Machine")
    st.caption("Replay quarter by quarter. Everything shown is limited to what was known at the as-of date.")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("⏮", help="Back to the first quarter", width="stretch"):
        st.session_state.q_idx, st.session_state.playing = 0, False
    if c2.button("⏸" if st.session_state.playing else "▶", help="Play / pause", width="stretch"):
        st.session_state.playing = not st.session_state.playing
        if st.session_state.playing and st.session_state.q_idx >= len(QUARTERS) - 1:
            st.session_state.q_idx = 0
    if c3.button("Step", help="Advance one quarter and reveal what resolved", width="stretch"):
        st.session_state.playing = False
        st.session_state.q_idx = min(st.session_state.q_idx + 1, len(QUARTERS) - 1)
    if c4.button("⏭", help="Jump to the end", width="stretch"):
        st.session_state.q_idx, st.session_state.playing = len(QUARTERS) - 1, False

    st.select_slider("As-of quarter", options=list(range(len(QUARTERS))), key="q_idx",
                     format_func=lambda i: qlabel(QUARTERS[i]))
    speed = st.slider("Seconds per quarter", 0.3, 3.0, 0.8, 0.1)
    AS_OF = QUARTERS[st.session_state.q_idx]
    st.metric("as_of", AS_OF.isoformat(), qlabel(AS_OF), delta_color="off")

    st.divider()
    st.subheader("Company and arm")
    query = st.text_input("Search companies", placeholder="anon_003 or a sector", key="company_query")
    shown = D.filter_companies(CTABLE, query)
    if shown.empty:
        st.warning("No company matches that search.")
        shown = CTABLE
    st.caption(f"{len(shown)} of {len(CTABLE)} companies")
    labels = dict(zip(shown["company_id"], shown["label"]))
    if st.session_state.get("company") not in labels:
        st.session_state.pop("company", None)
    company = st.selectbox("Company", list(labels), format_func=labels.get, key="company")
    arm = st.radio("Learned vs Frozen", ["learned", "frozen"], horizontal=True, key="arm",
                   help="Learned agents get corrections; the frozen twin is the same agent with no updates.")

    st.divider()
    st.subheader("Data")
    prov = bundle.provenance()
    st.caption(f"Source: `{'Postgres (DATABASE_URL)' if source == 'postgres' else Path(source).relative_to(ROOT) if Path(source).is_relative_to(ROOT) else source}`")
    if (CTABLE["sector"] == "unknown").all():
        st.caption("Sector unavailable: no `companies` table or `companies.jsonl` in this source.")
    st.caption(f"Runs: {len(bundle.runs)} · calls: {len(bundle.calls):,} · corrections: {len(bundle.corrections):,}")
    if stamp := D.source_stamp(source):
        st.caption(f"Files last written {time.strftime('%H:%M:%S', time.localtime(stamp))} "
                   f"({(time.time() - stamp) / 60:.0f} min ago); new rows load on the next rerun.")
    if prov:
        st.caption(f"metrics: {prov.get('metrics')} · grader: {prov.get('outcome_rule')} · llm: {prov.get('llm')}")
    if st.button("Reload data", width="stretch"):
        _load.clear()
        st.rerun()


# ---- header + honesty banners ---------------------------------------------------

st.title("Compounding Minds")
st.caption("A team of AI analysts that grades itself against reality and improves every time it's wrong.")

if not prov.get("real_results", False):
    st.markdown('<div class="cm-banner cm-warn"><b>NOT RESULTS.</b> These runs use stub metrics and a '
                'scripted LLM to exercise the pipeline. Do not quote these numbers.</div>', unsafe_allow_html=True)
if bundle.uses_fallback_updater():
    st.markdown('<div class="cm-banner cm-info"><b>Fallback updater.</b> Lessons were applied by the local '
                '<code>FakeModelUpdater</code> (principle memory), not by a Mubit model update.</div>',
                unsafe_allow_html=True)
PROGRESS = bundle.progress()
if PROGRESS["in_progress"]:
    lc = PROGRESS["last_complete"]
    st.markdown(f'<div class="cm-banner cm-info"><b>Replay in progress.</b> {PROGRESS["quarters_complete"]} '
                f'quarter(s) complete{f" (through {qlabel(lc)})" if lc else ""}; '
                f'{", ".join(qlabel(q) for q in PROGRESS["partial_quarters"])} still being written, so its calls '
                f'are partial and not yet graded. The view reloads as new rows land.</div>',
                unsafe_allow_html=True)

# Headline numbers at the current as_of
curves_now = D.accuracy_curves(bundle, AS_OF)
k = st.columns(4)
if not curves_now.empty:
    last = curves_now[curves_now["as_of"] == curves_now["as_of"].max()]
    la = last[last["variant"] == "learned"]
    fa = last[last["variant"] == "frozen"]
    la_acc = (la["rolling_accuracy"] * la["n_calls"]).sum() / la["n_calls"].sum() if la["n_calls"].sum() else None
    fa_acc = (fa["rolling_accuracy"] * fa["n_calls"]).sum() / fa["n_calls"].sum() if fa["n_calls"].sum() else None
    k[0].metric("Learned agents, rolling accuracy", pct(la_acc),
                None if la_acc is None or fa_acc is None else f"{(la_acc - fa_acc) * 100:+.1f} pts vs frozen twin")
    k[1].metric("Frozen twin, rolling accuracy", pct(fa_acc))
n_corr = len(D.visible_corrections(bundle, AS_OF))
k[2].metric("Corrections applied so far", f"{n_corr:,}")
k[3].metric("Quarter", f"{st.session_state.q_idx + 1} of {len(QUARTERS)}", qlabel(AS_OF), delta_color="off")

PREV = QUARTERS[st.session_state.q_idx - 1] if st.session_state.q_idx > 0 else None
fresh = D.just_resolved(bundle, PREV, AS_OF, arm, company)
with st.expander(f"Resolved at {qlabel(AS_OF)} for `{company}` ({arm}): {len(fresh)} call(s) graded "
                 f"against reality", expanded=len(fresh) > 0):
    if fresh.empty:
        st.caption("Nothing resolved for this company in this quarter. Press Step to move on.")
    else:
        for r in fresh.itertuples():
            st.markdown(f"**{r.agent}** · called {qlabel(r.as_of)}: **{r.answer}** at {pct(r.probability)} "
                        f"→ actual **{r.outcome}** {outcome_pill(r.correct)}", unsafe_allow_html=True)

tabs = st.tabs(["📈 Accuracy", "🏛 Committee", "🔁 Correction spotlight", "🧪 Held-out", "🏆 Scoreboard"])


# ---- 1. accuracy curves ---------------------------------------------------------

def shade_windows(fig: go.Figure) -> None:
    lo, hi = D.COVID_WINDOW
    fig.add_vrect(x0=lo, x1=hi, fillcolor="rgba(220,38,38,.08)", line_width=0,
                  annotation_text="COVID", annotation_position="top left")
    win = bundle.held_out_window()
    if win:
        fig.add_vrect(x0=win[0], x1=win[1], fillcolor="rgba(168,85,247,.07)", line_width=0,
                      annotation_text="held-out", annotation_position="top right")


with tabs[0]:
    left, right = st.columns([3, 1])
    with right:
        metric = st.radio("Metric", ["Accuracy", "Brier"], horizontal=True,
                          help="Accuracy: higher is better. Brier: lower is better.")
        window = st.slider("Rolling window (quarters)", 1, 8, 4)
        agent_pick = st.selectbox("Agent", ["All agents"] + AGENTS,
                                  format_func=lambda a: a if a == "All agents" else f"{a} ({D.INVESTOR[a]})")
    curves = D.accuracy_curves(bundle, AS_OF, window)
    col = "rolling_accuracy" if metric == "Accuracy" else "rolling_brier"
    with left:
        fig = go.Figure()
        shade_windows(fig)
        if agent_pick == "All agents":
            for arm in CURVE_ARMS:
                g = curves[curves["variant"] == arm]
                if g.empty:
                    continue
                agg = (g.assign(w=g[col] * g["n_calls"]).groupby("as_of")[["w", "n_calls"]].sum().reset_index())
                fig.add_scatter(x=agg["as_of"], y=agg["w"] / agg["n_calls"], name=arm, mode="lines+markers",
                                line=dict(color=ARM_COLOR[arm], width=3 if arm == "learned" else 2,
                                          dash=None if arm == "learned" else "dot"))
        else:
            for arm in CURVE_ARMS:
                g = curves[(curves["variant"] == arm) & (curves["agent"] == agent_pick)]
                if not g.empty:
                    fig.add_scatter(x=g["as_of"], y=g[col], name=arm, mode="lines+markers",
                                    line=dict(color=ARM_COLOR[arm], width=3 if arm == "learned" else 2,
                                              dash=None if arm == "learned" else "dot"))
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified",
                          legend=dict(orientation="h", y=1.08, x=0),
                          xaxis=dict(range=[QUARTERS[0], QUARTERS[-1]]),
                          yaxis=dict(title=f"rolling {metric.lower()}",
                                     tickformat=".0%" if metric == "Accuracy" else ".2f",
                                     range=[0, 1.02] if metric == "Accuracy" else None))
        st.plotly_chart(fig, width="stretch")
        st.caption("Learned agents receive corrections after every graded quarter; the frozen twin never does. "
                   "Same prompts, same data, same quarters."
                   + (" Baseline: no LLM, always the base answer (yes / base bucket)."
                      if "baseline" in set(curves["variant"]) else ""))

    st.subheader("Per agent")
    grid = st.columns(len(AGENTS))
    for i, a in enumerate(AGENTS):
        with grid[i]:
            g = curves[curves["agent"] == a]
            mini = go.Figure()
            for arm in ("learned", "frozen"):
                h = g[g["variant"] == arm]
                mini.add_scatter(x=h["as_of"], y=h[col], name=arm, mode="lines",
                                 line=dict(color=ARM_COLOR[arm], width=2.5 if arm == "learned" else 1.5,
                                           dash=None if arm == "learned" else "dot"))
            mini.update_layout(height=170, margin=dict(l=0, r=0, t=26, b=0), showlegend=False,
                               title=dict(text=f"{a} · {D.INVESTOR[a]}", font=dict(size=13)),
                               xaxis=dict(range=[QUARTERS[0], QUARTERS[-1]], showticklabels=False),
                               yaxis=dict(tickformat=".0%" if metric == "Accuracy" else ".2f",
                                          range=[0, 1.02] if metric == "Accuracy" else None))
            st.plotly_chart(mini, width="stretch", config={"displayModeBar": False})
            st.caption(f"model: `{D.model_version_at(bundle, a, AS_OF) or '–'}`")

    cq = D.corrections_by_quarter(bundle, AS_OF)
    if not cq.empty:
        st.subheader("Corrections fed back, per quarter")
        bar = go.Figure()
        for a in AGENTS:
            h = cq[cq["agent"] == a]
            bar.add_bar(x=h["as_of"], y=h["count"], name=a)
        bar.update_layout(barmode="stack", height=230, margin=dict(l=10, r=10, t=10, b=10),
                          legend=dict(orientation="h", y=1.15), xaxis=dict(range=[QUARTERS[0], QUARTERS[-1]]))
        st.plotly_chart(bar, width="stretch")


# ---- 2. committee table ---------------------------------------------------------

with tabs[1]:
    st.caption(f"Company and arm are set in the sidebar: `{company}`, {arm}.")
    res = D.committee(bundle, company, AS_OF, arm)
    if res["verdict"] is None:
        st.info(f"No {arm} calls for {company} at {AS_OF}. Pick another company or quarter.")
    else:
        v = res["verdict"]
        kind = {"attractive": "ok", "unattractive": "bad"}.get(v, "neutral")
        st.markdown(f"#### Committee verdict for `{company}` at {qlabel(AS_OF)}: {pill(v, kind)}",
                    unsafe_allow_html=True)
        m = st.columns(3)
        m[0].metric("Committee score", f"{res['score']:+.2f}", help="Weighted direction × probability, in [-1, 1]")
        m[1].metric("Confidence", pct(res["confidence"]), help="Heuristic until calibrated on the train window")
        m[2].metric("Resolved grades behind the weights", res["graded_weights"])
        if res["graded_weights"] == 0:
            st.caption("No grades had resolved by this date, so every agent carries the same weight.")

        for _, r in res["rows"].iterrows():
            with st.container(border=True):
                h1, h2, h3, h4 = st.columns([2.2, 1.2, 1.2, 1.2])
                d = D.direction(r["agent"], r["answer"])
                arrow = {1: "▲ good for the business", -1: "▼ bad for the business", 0: "● neutral"}[d]
                h1.markdown(f"**{r['agent'].title()}** · {D.INVESTOR[r['agent']]}  \n"
                            f"<span style='opacity:.7'>{D.QUESTION.get(r['agent'], r['question_id'])}</span>",
                            unsafe_allow_html=True)
                h2.markdown(f"Call: **{r['answer']}**  \n<span style='opacity:.7'>{arrow}</span>",
                            unsafe_allow_html=True)
                h3.markdown(f"Probability: **{pct(r['probability'])}**  \n"
                            f"weight {res['weights'].get(r['agent'], 0):.2f}")
                if D.is_resolved(r, AS_OF):
                    h4.markdown(f"Actual: **{r['outcome']}**  \n{outcome_pill(r['correct'])}", unsafe_allow_html=True)
                else:  # the replay must not reveal outcomes that land after the as-of date
                    h4.markdown(f"Actual: **pending**  \n{pill('not yet resolved', 'neutral')}",
                                unsafe_allow_html=True)
                with st.expander("Reasoning and evidence"):
                    for b in r["reasoning"]:
                        st.markdown(f"- {b}")
                    if r["evidence"]:
                        st.dataframe(pd.DataFrame(r["evidence"]), hide_index=True, width="stretch")
                    st.caption(f"principles: {', '.join(r['principles_used']) or '–'} · model: `{r['model']}`")


# ---- 3. correction spotlight ----------------------------------------------------

with tabs[2]:
    corr = D.visible_corrections(bundle, AS_OF)
    if bundle.corrections.empty:
        st.info("No corrections stored yet.")
    else:
        visible = corr.sort_values("as_of")
        if visible.empty:
            st.info(f"No corrections had been made by {AS_OF}. Move the replay forward.")
        else:
            f1, f2 = st.columns(2)
            ag = f1.selectbox("Agent", ["any"] + sorted(visible["agent"].unique()), key="spot_agent")
            co = f2.selectbox("Company", ["any"] + sorted(visible["company_id"].unique()), key="spot_co")
            pool = visible[((visible["agent"] == ag) | (ag == "any")) & ((visible["company_id"] == co) | (co == "any"))]
            if pool.empty:
                st.info("No corrections match those filters.")
            else:
                labels = {r.correction_id: f"{qlabel(r.as_of)} · {r.agent} · {r.company_id} · {r.error_type}"
                          for r in pool.iloc[::-1].itertuples()}
                cid = st.selectbox("Correction", list(labels), format_func=labels.get, key="spot_cid")
                s = D.correction_story(bundle, cid)
                c, b, a, fz = s["correction"], s["before"], s["after"], s["frozen_after"]
                if a is not None and a["as_of"] > AS_OF:  # later than the replay clock: not yet shown
                    a, fz = None, None

                cols = st.columns(5)
                with cols[0]:
                    st.markdown(f'<div class="cm-step"><h4>1 · Original call</h4>'
                                f'<b>{b["answer"]}</b> at {pct(b["probability"])}<br>'
                                f'<small>{b["agent"]} · {b["company_id"]} · {qlabel(b["as_of"])}</small></div>',
                                unsafe_allow_html=True)
                with cols[1]:
                    st.markdown(f'<div class="cm-step"><h4>2 · What happened</h4>'
                                f'<b>{b["outcome"]}</b> {outcome_pill(b["correct"])}<br>'
                                f'<small>Brier {num(b["brier"])}</small></div>', unsafe_allow_html=True)
                with cols[2]:
                    st.markdown(f'<div class="cm-step"><h4>3 · Lesson</h4>{c["summary"]}<br>'
                                f'<small>{c["error_type"]} · refs {", ".join(c["principle_refs"]) or "–"}</small></div>',
                                unsafe_allow_html=True)
                with cols[3]:
                    ref = c["mubit_ref"] or "–"
                    tag = " " + pill("fallback", "neutral") if D.is_fallback(ref, b["model"]) else ""
                    st.markdown(f'<div class="cm-step"><h4>4 · Model update</h4><code>{ref}</code>{tag}<br>'
                                f'<small><code>{b["model"]}</code> → '
                                f'<code>{a["model"] if a is not None else "–"}</code></small></div>',
                                unsafe_allow_html=True)
                with cols[4]:
                    if a is None:
                        body = "No later call visible yet. Step the replay forward."
                    else:
                        body = (f'<b>{a["answer"]}</b> at {pct(a["probability"])} {outcome_pill(a["correct"])}<br>'
                                f'<small>{qlabel(a["as_of"])} · Brier {num(a["brier"])}</small>')
                        if fz is not None:
                            body += (f'<br><small>frozen twin: {fz["answer"]} at {pct(fz["probability"])} '
                                     f'{outcome_pill(fz["correct"])}</small>')
                    st.markdown(f'<div class="cm-step"><h4>5 · Asked again</h4>{body}</div>', unsafe_allow_html=True)

                st.write("")
                l, r = st.columns(2)
                with l:
                    st.markdown("**Before: reasoning**")
                    for x in b["reasoning"]:
                        st.markdown(f"- {x}")
                    snap = c["payload"].get("inputs_snapshot", {}).get("metrics", [])
                    if snap:
                        st.caption("Metrics the agent saw (computed in Python, point-in-time)")
                        st.dataframe(pd.DataFrame(snap)[["name", "value", "unit", "as_of"]],
                                     hide_index=True, width="stretch")
                with r:
                    st.markdown("**After: reasoning**")
                    if a is not None:
                        for x in a["reasoning"]:
                            st.markdown(f"- {x}")
                        st.caption(f"principles: {', '.join(a['principles_used'])}")
                    with st.expander("Grader evidence"):
                        st.json(b["grade_evidence"])


    st.divider()
    with st.expander("Run the loop for this company and quarter", expanded=False):
        nxt = QUARTERS[st.session_state.q_idx + 1] if st.session_state.q_idx + 1 < len(QUARTERS) else None
        st.caption("Runs call, grade, correction, model update, re-ask once, on the offline path: scripted LLM, "
                   "stub metrics, fallback updater. No network calls, nothing is saved.")
        la = st.selectbox("Agent", AGENTS, key="loop_agent")
        if nxt is None:
            st.info("This is the last quarter, so there is no next quarter to re-ask. Step back first.")
        if st.button(f"Run loop: {la} on {company}, {qlabel(AS_OF)} → {qlabel(nxt) if nxt else '?'}",
                     disabled=nxt is None, type="primary"):
            try:
                with st.spinner("Running the loop…"):
                    st.session_state.loop_result = D.run_live_loop(la, company, AS_OF, nxt)
            except Exception as e:  # noqa: BLE001
                st.session_state.loop_result = {"error": f"{type(e).__name__}: {e}"}
        lr = st.session_state.get("loop_result")
        if lr and lr.get("error"):
            st.error(f"The loop failed: {lr['error']}")
        elif lr:
            def _call_line(label, call, grade):
                if not call:
                    st.markdown(f"**{label}**: no valid call (dropped).")
                    return
                cl = call["claim"]
                g = (f" → actual **{grade['outcome']}** "
                     f"{outcome_pill(grade['correct'])}") if grade else ""
                st.markdown(f"**{label}** ({call['agent']}, {call['company_id']}, {call['as_of']}): "
                            f"**{cl['answer']}** at {pct(cl.get('probability'))}{g}", unsafe_allow_html=True)
                for x in call.get("reasoning", []):
                    st.markdown(f"- {x}")
            _call_line("1 · First call", lr["before"], lr["before_grade"])
            if not lr["corrections"]:
                st.success("No correction: the first call was right, dropped or unresolvable.")
            for cc in lr["corrections"]:
                st.markdown(f"**2 · Lesson** ({cc['error_type']}): {cc['lesson']}")
            ref = (lr.get("update_ref") or {}).get("ref")
            if ref:
                st.markdown(f"**3 · Model update** `{ref}` ({lr.get('update_state')}) "
                            f"{pill('fallback', 'neutral') if D.is_fallback(ref, lr['version_before']) else ''}",
                            unsafe_allow_html=True)
            st.markdown(f"Model version: `{lr['version_before']}` → `{lr['version_after']}`")
            _call_line("4 · Asked again", lr["after"], lr["after_grade"])


# ---- 4. held-out panel ----------------------------------------------------------

with tabs[3]:
    hpath, rep, why = D.find_heldout_report()
    if rep is None and not bundle.eval_results.empty:
        er = bundle.eval_results.sort_values("generated_at").iloc[-1]
        rep, hpath = er["report"], None
    if rep is None:
        st.info("No held-out report yet. Expected `eval/reports/heldout_report.json` (or run "
                "`python -m eval.run --save data/runs`).")
        if why and why != "no report file found":
            st.warning(f"A report file exists but could not be read: {why}")
    else:
        split = rep.get("split", {})
        real = bool((rep.get("provenance") or {}).get("real_results", False))
        if not real:
            st.markdown(f'<div class="cm-banner cm-warn">{rep.get("banner") or "NOT RESULTS. Stub inputs: do not quote these numbers."}</div>',
                        unsafe_allow_html=True)
        st.caption(f"Source: `{hpath.relative_to(ROOT) if hpath else 'stored eval_results'}` · generated "
                   f"{rep.get('generated_at', '?')}")
        tw, hw = split.get("train_window") or ["?", "?"], split.get("held_out_window") or ["?", "?"]
        st.caption(f"Train {tw[0]} → {tw[1]} · held-out {hw[0]} → {hw[1]} · "
                   f"{len(split.get('train_companies', []))} train companies, "
                   f"{len(split.get('held_out_companies', []))} never seen")
        seg_names = {"all_companies": "All companies", "seen_companies": "Seen in training",
                     "unseen_companies": "Never seen"}
        seg = st.radio("Segment", list(seg_names), format_func=seg_names.get, horizontal=True)
        rep_agents = [a for a in AGENTS if a in rep.get("agents", {})]
        if not rep_agents:
            st.info("The report has no agents yet.")
        summary = []
        for a in rep_agents:
            t = D.heldout_table(rep, a, seg)
            if not t.empty:
                summary.append(t.assign(agent=a))
        if summary:
            df = pd.concat(summary)
            fig = go.Figure()
            colors = {"frozen": FROZEN, "learned": LEARNED, "frontier": FRONTIER,
                      "baseline: always_yes": "#f59e0b", "baseline: base_rate": "#10b981"}
            for armname in df["arm"].unique():
                h = df[df["arm"] == armname]
                fig.add_bar(x=h["agent"], y=h["accuracy"], name=armname, marker_color=colors.get(armname))
            fig.update_layout(barmode="group", height=360, margin=dict(l=10, r=10, t=10, b=10),
                              yaxis=dict(tickformat=".0%", range=[0, 1.05], title="accuracy"),
                              legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, width="stretch")
        elif rep_agents:
            st.info("No results in this segment.")
        for a in rep_agents:
            info = rep["agents"][a]
            t = D.heldout_table(rep, a, seg)
            with st.expander(f"{a} · {D.INVESTOR[a]} · {info.get('corrections_applied', 0)} corrections in training · "
                             f"{info.get('learned_version_start')} → {info.get('learned_version_end')}"):
                if not t.empty:
                    st.dataframe(t.style.format({"accuracy": "{:.1%}", "brier": "{:.3f}"}),
                                 hide_index=True, width="stretch")
                    diff = info["segments"][seg].get("learned_minus_frozen", {})
                    st.caption(f"Learned minus frozen: accuracy {(diff.get('accuracy') or 0) * 100:+.1f} pts, "
                               f"Brier {(diff.get('brier') or 0):+.3f} (lower is better)")


# ---- 5. legend scoreboard -------------------------------------------------------

with tabs[4]:
    w = st.slider("Look-back (quarters)", 1, 8, 4, key="sb_window")
    sb = D.scoreboard(bundle, AS_OF, arm, w)
    st.markdown(f"Which investor's rules are working best over the {w} quarters up to **{qlabel(AS_OF)}**.")
    if sb.empty:
        st.info("No graded calls yet at this date.")
    else:
        for rank, r in enumerate(sb.itertuples(), 1):
            with st.container(border=True):
                c = st.columns([0.4, 2, 1, 1, 1, 1])
                c[0].markdown(f"### {['🥇', '🥈', '🥉'][rank - 1] if rank <= 3 else rank}")
                c[1].markdown(f"**{r.investor}**  \n<span style='opacity:.7'>{r.agent}</span>", unsafe_allow_html=True)
                c[2].metric("Accuracy", pct(r.accuracy))
                c[3].metric("Brier", num(r.brier))
                c[4].metric("Graded calls", r.calls)
                c[5].metric("Corrections so far", r.corrections)


# ---- play loop ------------------------------------------------------------------

if st.session_state.playing:
    if st.session_state.q_idx < len(QUARTERS) - 1:
        time.sleep(speed)
        st.session_state._advance = True
        st.rerun()
    else:
        st.session_state.playing = False
        st.rerun()
