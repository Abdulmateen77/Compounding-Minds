import { STANCE_COLOR } from "../api/client";
import { CALL_COLOR, type Lens } from "../research";
import { counts, cut, stanceOf } from "../scene/lenses";
import { Avatar } from "./Avatar";
import { myWhy } from "./firstPerson";

/* The five investors in one row under the office: face, name, call and a line of why. It reads straight from the report, so it is
   complete the moment the page opens. While the debate plays, whoever is speaking lights up here too. A card opens that investor's
   analysis (and, from there, the ask box). */

const call = (l: Lens) => (l.decision ? CALL_COLOR[l.decision.call] : STANCE_COLOR[stanceOf(l.fit)]);

export function PanelDeck({ lenses, speaking, onOpen }: { lenses: Lens[]; speaking: number | null; onOpen: (i: number) => void }) {
  return (
    <ul className="m-0 p-0 list-none grid gap-3 grid-cols-2 md:grid-cols-3 xl:grid-cols-5" aria-label="The investors. Choose one to open their analysis.">
      {lenses.map((l, i) => {
        const c = call(l), { pass, known } = counts(l), live = speaking === i, why = myWhy(l);
        return (
          <li key={l.key} className="grid">
            <button onClick={() => onOpen(i)} aria-haspopup="dialog" aria-label={`${l.name}: ${l.decision?.label ?? l.word}. Open their analysis.`}
              className="card text-left p-3 grid gap-2 content-start cursor-pointer"
              style={{
                color: "var(--foreground)", borderTop: `4px solid ${c}`, gridTemplateRows: "auto 3.9rem auto",
                boxShadow: live ? `0 0 0 2px ${c}` : undefined, transform: live ? "translateY(-3px)" : undefined,
                transition: "box-shadow var(--duration) ease-out, transform var(--duration) ease-out",
              }}>
              <span className="flex items-center gap-2 min-w-0">
                <Avatar l={l} size={40} ring={c} />
                <span className="grid leading-tight min-w-0">
                  <span className="font-semibold text-sm truncate">{l.name}</span>
                  <span className="text-sm font-semibold" style={{ color: c }}>{l.decision?.label ?? l.word}</span>
                </span>
              </span>
              <span className="text-xs leading-snug mute" style={{ display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                {live ? "Speaking now…" : why ? `“${cut(why, 110)}.”` : l.question}
              </span>
              <span className="flex items-center justify-between gap-2 text-xs pt-2" style={{ borderTop: "1px solid var(--divider)" }}>
                <span className="num mute">{l.fit == null ? "no data" : `${pass} of ${known} checks`}</span>
                <span style={{ color: "var(--primary)" }}>Open</span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
