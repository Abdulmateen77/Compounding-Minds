import { STANCE_COLOR } from "../api/client";
import { AnalysisPopup } from "../components/AnalysisPopup";
import { opening } from "../components/firstPerson";
import { Avatar } from "../components/Avatar";
import { CALL_COLOR, type Lens } from "../research";
import { MARK, checkLabel, counts, cut, stanceOf, typed } from "./lenses";
import { agentState, checkState, type Timeline } from "./timeline";

/* Under the scene on the Investor panel tab: one card per investor, with their face and name, what they are thinking right now
   (the check they are on and what it found, then their reading as they give it) and their vote once they have given it. Every card
   is the same fixed height, so the page does not shift while the prologue plays. A card, or the investor in the scene, opens their
   analysis as a pop-up. */

type Props = {
  lenses: Lens[]; tl: Timeline; t: number; unlocked: boolean;
  open: number | null; setOpen: (i: number | null) => void; onAsk?: (i: number) => void;
};

export function ThinkingCards({ lenses, tl, t, unlocked, open, setOpen, onAsk }: Props) {
  return (
    <section className="grid gap-3 mt-3" aria-label="What each investor is thinking">
      <ul className="m-0 p-0 list-none grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5" aria-label="The investors. Choose one to see their analysis and vote.">
        {lenses.map((l, i) => {
          // "thinking" only inside their own research window; before it they are still waiting their turn
          const raw = unlocked ? "done" : agentState(tl, i, t);
          const st = raw === "thinking" && t < tl.speak[i] - tl.thinkLen[i] ? "idle" : raw;
          const voted = st === "done" || st === "speaking";
          const c = voted && l.decision ? CALL_COLOR[l.decision.call] : STANCE_COLOR[stanceOf(l.fit)];
          const live = st === "thinking" || st === "speaking", { pass, known } = counts(l);
          return (
            <li key={l.key} className="contents">
              <button onClick={() => setOpen(i)} aria-haspopup="dialog"
                className="card text-left p-3 grid gap-2 cursor-pointer"
                style={{ color: "var(--text)", gridTemplateRows: "auto 7.25rem auto", borderColor: live ? c : undefined,
                  boxShadow: live ? `0 0 0 1px ${c}` : undefined, transition: "border-color .4s, box-shadow .4s" }}>
                <span className="flex items-center gap-2 min-w-0">
                  <Avatar l={l} size={38} ring={live || voted ? c : undefined} />
                  <span className="grid leading-tight min-w-0">
                    <span className="font-semibold text-sm truncate">{l.name}</span>
                    <span className="mute text-[11px] truncate">{st === "idle" ? "Waiting their turn" : st === "thinking" ? "Working through their checks" : st === "speaking" ? "Giving their reading" : `${pass} of ${known} checks passed`}</span>
                  </span>
                </span>
                <span className="overflow-hidden">
                  <Thinking key={st} l={l} i={i} st={st} tl={tl} t={t} />
                </span>
                <span className="grid gap-0.5 text-xs pt-1.5" style={{ borderTop: "1px solid var(--line)" }}>
                  <span>Vote: <b style={{ color: voted ? c : "var(--mute)", transition: "color .4s" }}>{voted ? (l.decision?.label ?? l.word) : "not yet"}</b></span>
                  <span style={{ color: "var(--blue)" }}>See their analysis</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {open != null && lenses[open] && (
        <AnalysisPopup l={lenses[open]} onClose={() => setOpen(null)}
          onAsk={onAsk && unlocked ? () => { const i = open; setOpen(null); onAsk(i); } : undefined} />
      )}
    </section>
  );
}

const clamp = (lines: number) => ({ display: "-webkit-box", WebkitLineClamp: lines, WebkitBoxOrient: "vertical" as const, overflow: "hidden" });

/** The thinking line: the check they are on (question, then what it found), their reading as it is typed, or their reading. */
function Thinking({ l, i, st, tl, t }: { l: Lens; i: number; st: string; tl: Timeline; t: number }) {
  const reading = opening(l);                                   // in their own words: the call, why, one point each way
  const fade = { animation: "fadein .35s ease-out" };
  if (st === "idle") return <span className="mute text-xs block" style={{ ...fade, ...clamp(5) }}>{l.question}</span>;
  if (st === "speaking") return <span className="text-xs leading-snug block" style={{ ...fade, ...clamp(6) }}>“{typed(reading, t - tl.speak[i], 75)}</span>;
  if (st === "done") return <span className="text-xs leading-snug block" style={{ ...fade, ...clamp(6) }}>“{reading}”</span>;
  const m = l.checks.length, s = checkState(tl, i, t, m);
  if (!s || m === 0) return <span className="mute text-xs block">{l.question}</span>;
  const at = Math.min(m - 1, s.current ?? Math.max(0, s.done - 1)), k = l.checks[at];
  const asking = s.current == null ? s.done === 0 : s.current >= s.done;
  const M = MARK[k.result];
  return (
    <span className="grid gap-1 text-xs leading-snug" style={fade}>
      <span className="h-1 rounded-full overflow-hidden" style={{ background: "var(--line)" }} aria-hidden>
        <span className="block h-full" style={{ width: `${Math.min(1, (s.done + (s.current != null ? s.phase : 0)) / m) * 100}%`, background: "var(--blue)", transition: "width .25s linear" }} />
      </span>
      <span style={clamp(2)}><span className="mute">Check {at + 1} of {m}:</span> {checkLabel(k)}</span>
      <span key={`${at}-${asking}`} style={{ ...fade, ...clamp(3) }}>
        {asking
          ? <span className="mute">Looking at the filings…</span>
          : <><span style={{ color: M.color }} aria-hidden>{M.mark}</span> <span className="num">{cut(k.shown, 90)}</span></>}
      </span>
    </span>
  );
}
