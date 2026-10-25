import { useEffect, useRef } from "react";
import { CALL_COLOR, type Lens } from "../research";
import { MARK, counts, surname } from "../scene/lenses";
import { Avatar } from "./Avatar";
import { forAndAgainst, myCall, myWatch, myWhy, said } from "./firstPerson";

/** One investor's analysis, in their own voice, as a pop-up: the call and why, the strongest points each way, what they would
    watch, and every check behind it folded away. Esc, the backdrop or Close shuts it. */
export function AnalysisPopup({ l, onClose, onAsk }: { l: Lens; onClose: () => void; onAsk?: () => void }) {
  const color = l.decision ? CALL_COLOR[l.decision.call] : "var(--muted)", { pass, known } = counts(l);
  const { pros, cons } = forAndAgainst(l), watch = myWatch(l), why = myWhy(l);
  const close = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    close.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); prev?.focus({ preventScroll: true }); };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[var(--z-modal)] grid place-items-center p-4" style={{ background: "rgba(5,7,13,.55)", animation: "fadein .15s ease-out" }}
      onClick={onClose}>
      <article role="dialog" aria-modal="true" aria-label={`${l.name}'s analysis`} onClick={(e) => e.stopPropagation()}
        className="card w-full max-w-xl max-h-[85vh] overflow-y-auto p-5 grid gap-4"
        style={{ borderTop: `4px solid ${color}`, animation: "popin var(--duration-fast) ease-out" }}>
        <header className="flex items-center gap-3">
          <Avatar l={l} size={52} ring={color} />
          <div className="grid min-w-0 flex-1">
            <b className="text-base leading-tight">{l.name}</b>
            <span className="mute text-xs">{l.question}</span>
          </div>
          <button ref={close} className="btn ghost" onClick={onClose} aria-label="Close">Close</button>
        </header>

        <section className="rounded-xl p-3 grid gap-1" style={{ background: `color-mix(in srgb, ${color} 10%, transparent)` }}>
          <b className="text-lg" style={{ color }}>{myCall(l)}.</b>
          {why && <span className="text-sm">{why}.</span>}
          <span className="num mute text-xs">{pass} of {known} of my checks passed</span>
        </section>

        <div className="grid gap-4 sm:grid-cols-2">
          <Points title="In its favour" items={pros} empty="Nothing clearly in its favour on my checks." />
          <Points title="Against it" items={cons} empty="Nothing against it on my checks." />
        </div>

        {watch && <p className="m-0 text-sm"><b>What I'd watch next.</b> {watch}</p>}

        <details className="text-xs">
          <summary className="cursor-pointer mute">All {l.checks.length} of my checks</summary>
          <ul className="m-0 mt-2 p-0 list-none grid gap-2">
            {l.checks.map((k) => (
              <li key={k.id} className="flex gap-2 items-start">
                <span style={{ color: MARK[k.result].color }} aria-hidden>{MARK[k.result].mark}</span>
                <span>{said(k)}<span className="mute"> · {k.principle}</span></span>
              </li>
            ))}
          </ul>
        </details>

        <footer className="flex items-center justify-between gap-3 flex-wrap">
          <span className="mute text-xs">My rules applied to the filings: a reading of the evidence, not personal advice.</span>
          {onAsk && <button className="btn" onClick={onAsk}>Question {surname(l)}</button>}
        </footer>
      </article>
    </div>
  );
}

function Points({ title, items, empty }: { title: string; items: Lens["checks"]; empty: string }) {
  return (
    <section className="grid gap-2 content-start">
      <b className="text-sm">{title}</b>
      {items.length === 0 && <span className="mute text-xs">{empty}</span>}
      <ul className="m-0 p-0 list-none grid gap-2 text-xs leading-snug">
        {items.map((k) => (
          <li key={k.id} className="flex gap-2 items-start">
            <span style={{ color: MARK[k.result].color }} aria-hidden>{MARK[k.result].mark}</span>
            <span>{said(k)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
