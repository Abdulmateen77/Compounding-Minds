import { STANCE_COLOR } from "../api/client";
import type { Lens } from "../research";
import { counts, stanceOf, surname } from "../scene/lenses";

/** The investors as real, focusable buttons: a keyboard and screen-reader route to each one's reading and chat, whether or not the
    3D scene can run. Colour is never the only signal: each card also says the reading in words and shows the fit as a number. */
export function InvestorRoster({ lenses, sel, onChoose, locked = false }: { lenses: Lens[]; sel: number | null; onChoose: (i: number) => void; locked?: boolean }) {
  return (
    <ul className="m-0 p-0 list-none grid gap-2 grid-cols-2 sm:grid-cols-3 lg:grid-cols-6" aria-label={locked ? "The investors. You can question them when the prologue ends." : "The investors. Choose one to question them."}>
      {lenses.map((l, i) => {
        const c = STANCE_COLOR[stanceOf(l.fit)], { pass, known } = counts(l), on = sel === i;
        return (
          <li key={l.key} className="contents">
            <button onClick={() => onChoose(i)} aria-pressed={on} disabled={locked}
              aria-label={locked ? `${l.name}. You can question them when the prologue ends.` : `Ask ${l.name}. Reading: ${l.word}. ${pass} of ${known} checks passed.`}
              className={`card text-left p-3 grid gap-1 transition-transform ${locked ? "cursor-not-allowed" : "cursor-pointer hover:-translate-y-0.5"}`}
              style={{ minHeight: 76, borderColor: on ? c : undefined, boxShadow: on ? `0 0 0 2px ${c}` : undefined, color: "var(--foreground)", opacity: locked ? 0.55 : 1 }}>
              <span className="flex items-center gap-2">
                <span aria-hidden className="inline-grid place-items-center w-7 h-7 rounded-full text-xs font-bold shrink-0" style={{ background: `color-mix(in srgb, ${c} 22%, transparent)`, color: c }}>{surname(l)[0]}</span>
                <span className="font-semibold text-sm leading-tight">{surname(l)}</span>
              </span>
              <span className="text-xs font-medium" style={{ color: c }}>{l.word}</span>
              <span className="num mute text-xs">{l.fit == null ? "no data" : `fit ${Math.round(l.fit * 100)}%`} · {pass}/{known} checks</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
