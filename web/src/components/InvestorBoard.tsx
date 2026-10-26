import { motion } from "framer-motion";
import { STANCE_COLOR } from "../api/client";
import { DUR, EASE_SOFT } from "../motion";
import { useReducedMotion } from "../route";
import { CALL_COLOR, type Lens } from "../research";
import { counts, stanceOf, surname } from "../scene/lenses";
import { Avatar } from "./Avatar";
import { opening } from "./firstPerson";
import { Say } from "./Say";

/* The investors at a glance: who they are, the call they make, and why in their own words. It reads straight from the report, so it
   is complete the moment the page opens and never waits on the 3D scene. Each card opens that investor's full analysis, or goes to the
   ask box with them already chosen. */

const call = (l: Lens) => (l.decision ? CALL_COLOR[l.decision.call] : STANCE_COLOR[stanceOf(l.fit)]);

export function InvestorBoard({ lenses, onAnalysis, onAsk }: { lenses: Lens[]; onAnalysis: (i: number) => void; onAsk: (i: number) => void }) {
  const still = useReducedMotion();
  return (
    <section className="grid gap-3" aria-label="The investors">
      <div>
        <h2 className="text-xl font-semibold m-0">The investors</h2>
        <p className="mute text-sm m-0 mt-1 max-w-3xl">Each one applies their own rules to the same filings. Open an analysis for every check, or ask one of them why.</p>
      </div>
      <ul className="m-0 p-0 list-none grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {lenses.map((l, i) => {
          const c = call(l), { pass, known } = counts(l);
          return (
            <motion.li key={l.key} className="grid" initial={still ? false : { opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-40px" }}
              transition={{ duration: DUR.slower, ease: EASE_SOFT, delay: still ? 0 : i * 0.07 }}>
              <article className="card p-4 grid gap-3 content-start" style={{ borderTop: `4px solid ${c}`, gridTemplateRows: "auto 1fr auto" }}>
                <header className="flex items-center gap-3 min-w-0">
                  <motion.span className="shrink-0" animate={still ? undefined : { y: [0, -4, 0] }} transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut", delay: i * 0.4 }}>
                    <Avatar l={l} size={56} ring={c} />
                  </motion.span>
                  <div className="grid min-w-0 leading-tight">
                    <h3 className="m-0 text-base font-semibold truncate">{l.name}</h3>
                    <span className="text-sm font-semibold" style={{ color: c }}>{l.decision?.label ?? l.word}</span>
                    <span className="num mute text-xs">{l.fit == null ? "no data" : `${pass} of ${known} checks passed`}</span>
                  </div>
                </header>
                <p className="m-0 text-sm leading-relaxed">“<Say>{opening(l)}</Say>”</p>
                <footer className="flex items-center justify-between gap-2 flex-wrap pt-3" style={{ borderTop: "1px solid var(--divider)" }}>
                  <button className="btn ghost sm" onClick={() => onAnalysis(i)} aria-haspopup="dialog">Full analysis</button>
                  <button className="btn sm" onClick={() => onAsk(i)}>Ask {surname(l)}</button>
                </footer>
              </article>
            </motion.li>
          );
        })}
      </ul>
    </section>
  );
}
