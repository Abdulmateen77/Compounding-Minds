import { useState } from "react";
import { STANCE_COLOR } from "../api/client";
import { PanellistCard } from "../components/InvestorCards";
import { CALL_COLOR, type Lens } from "../research";
import { MARK, checkLabel, counts, cut, stanceOf, surname, typed } from "./lenses";
import { agentState, checkState, type Timeline } from "./timeline";

/* Under the scene on the Investor panel tab: one card per investor, with their avatar and name, what they are thinking right now
   (the check they are on and what it found, then their reading as they give it) and their vote once they have given it. Click a
   card for everything they came up with: every check, the idea behind it, their view and their call. */

type Props = { lenses: Lens[]; readings: string[]; tl: Timeline; t: number; unlocked: boolean; onAsk?: (i: number) => void };

export function ThinkingCards({ lenses, readings, tl, t, unlocked, onAsk }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const chosen = lenses.findIndex((l) => l.key === open);
  return (
    <section className="grid gap-3 mt-3" aria-label="What each investor is thinking">
      <ul className="m-0 p-0 list-none grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5" aria-label="The investors. Choose one to see their checks and their vote.">
        {lenses.map((l, i) => {
          // "thinking" only inside their own research window; before it they are still waiting their turn
          const raw = unlocked ? "done" : agentState(tl, i, t);
          const st = raw === "thinking" && t < tl.speak[i] - tl.thinkLen[i] ? "idle" : raw;
          const voted = st === "done" || st === "speaking";
          const c = voted && l.decision ? CALL_COLOR[l.decision.call] : STANCE_COLOR[stanceOf(l.fit)];
          const live = st === "thinking" || st === "speaking", on = open === l.key, { pass, known } = counts(l);
          return (
            <li key={l.key} className="contents">
              <button onClick={() => setOpen(on ? null : l.key)} aria-expanded={on}
                className="card text-left p-3 grid gap-2 content-start cursor-pointer"
                style={{ color: "var(--text)", borderColor: on || live ? c : undefined, boxShadow: on ? `0 0 0 2px ${c}` : live ? `0 0 0 1px ${c}` : undefined }}>
                <span className="flex items-center gap-2">
                  <span aria-hidden className="inline-grid place-items-center w-9 h-9 rounded-full font-bold shrink-0" style={{ background: `color-mix(in srgb, ${c} 22%, transparent)`, color: c }}>{surname(l)[0]}</span>
                  <span className="grid leading-tight min-w-0">
                    <span className="font-semibold text-sm">{l.name}</span>
                    <span className="mute text-[11px]">{st === "idle" ? "Waiting their turn" : st === "thinking" ? "Working through their checks" : st === "speaking" ? "Giving their reading" : `${pass} of ${known} checks passed`}</span>
                  </span>
                </span>
                <Thinking l={l} i={i} st={st} reading={readings[i]} tl={tl} t={t} />
                <span className="grid gap-0.5 text-xs pt-1.5" style={{ borderTop: "1px solid var(--line)" }}>
                  <span>Vote: <b style={{ color: voted ? c : "var(--mute)" }}>{voted ? (l.decision?.label ?? l.word) : "not yet"}</b></span>
                  <span style={{ color: "var(--blue)" }}>{on ? "Hide their analysis" : "See their checks and vote"}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {chosen >= 0 && (
        <div className="grid gap-2">
          <PanellistCard l={lenses[chosen]} wide />
          {onAsk && unlocked && (
            <div><button className="btn ghost" onClick={() => onAsk(chosen)}>Question {surname(lenses[chosen])} one-on-one</button></div>
          )}
        </div>
      )}
    </section>
  );
}

/** The thinking line: the check they are on (question, then what it found), their reading as it is typed, or their reading. */
function Thinking({ l, i, st, reading, tl, t }: { l: Lens; i: number; st: string; reading: string; tl: Timeline; t: number }) {
  if (st === "idle") return <span className="mute text-xs">{l.question}</span>;
  if (st === "speaking") return <span className="text-xs leading-snug">{typed(reading, t - tl.speak[i], 65)}</span>;
  if (st === "done") return <span className="text-xs leading-snug">{cut(reading, 190)}</span>;
  const m = l.checks.length, s = checkState(tl, i, t, m);
  if (!s || m === 0) return <span className="mute text-xs">{l.question}</span>;
  const at = Math.min(m - 1, s.current ?? Math.max(0, s.done - 1)), k = l.checks[at];
  const asking = s.current == null ? s.done === 0 : s.current >= s.done;
  const M = MARK[k.result];
  return (
    <span className="grid gap-1 text-xs leading-snug">
      <span className="h-1 rounded-full overflow-hidden" style={{ background: "var(--line)" }} aria-hidden>
        <span className="block h-full" style={{ width: `${Math.min(1, (s.done + (s.current != null ? s.phase : 0)) / m) * 100}%`, background: "var(--blue)" }} />
      </span>
      <span><span className="mute">Check {at + 1} of {m}:</span> {k.check}</span>
      {asking
        ? <span className="mute">Looking at the filings…</span>
        : <span><span style={{ color: M.color }} aria-hidden>{M.mark}</span> <b className="font-medium">{checkLabel(k)}</b> <span className="num mute">{cut(k.shown, 70)}</span></span>}
    </span>
  );
}
