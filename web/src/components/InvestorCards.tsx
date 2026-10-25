import { useState } from "react";
import { STANCE_COLOR } from "../api/client";
import { CALL_COLOR, type Check, type Lens } from "../research";
import { MARK, checkLabel, counts, cut, stanceOf, surname } from "../scene/lenses";

/* Everything each investor analysed, in two forms: a row of boxes (avatar, name, their call) that open the full card, and
   the cards themselves. Everything comes from the report: the checks, the investor's guide and the written view. */

const firstSentence = (text?: string | null) => {
  const t = text?.trim();
  if (!t) return null;
  // a sentence ends at . ! or ? followed by a space and a capital letter (so "25.5%" and "3.8x" never cut it short)
  const s = t.match(/^[\s\S]+?[.!?](?=\s+[A-Z“"]|\s*$)/)?.[0] ?? t;
  return cut(s.trim(), 220);
};

export function CallChip({ l, big = false }: { l: Lens; big?: boolean }) {
  if (!l.decision) return null;
  const c = CALL_COLOR[l.decision.call];
  return (
    <span className={`chip shrink-0 ${big ? "text-sm px-3 py-1" : ""}`} style={{ color: c, borderColor: c, background: `color-mix(in srgb, ${c} 10%, transparent)` }}>
      {l.decision.label}
    </span>
  );
}

/** The panellists as boxes; choosing one opens their full card below the row. */
export function InvestorBoxes({ lenses }: { lenses: Lens[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const chosen = lenses.find((l) => l.key === open);
  return (
    <div className="grid gap-3">
      <ul className="m-0 p-0 list-none grid gap-2 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5" aria-label="The investors. Choose one to see their full analysis.">
        {lenses.map((l) => {
          const c = l.decision ? CALL_COLOR[l.decision.call] : STANCE_COLOR[stanceOf(l.fit)], on = open === l.key, { pass, known } = counts(l);
          return (
            <li key={l.key} className="contents">
              <button onClick={() => setOpen(on ? null : l.key)} aria-expanded={on}
                className="card text-left p-3 grid gap-1.5 cursor-pointer transition-transform hover:-translate-y-0.5"
                style={{ color: "var(--text)", borderColor: on ? c : undefined, boxShadow: on ? `0 0 0 2px ${c}` : undefined }}>
                <span className="flex items-center gap-2">
                  <span aria-hidden className="inline-grid place-items-center w-9 h-9 rounded-full font-bold shrink-0" style={{ background: `color-mix(in srgb, ${c} 22%, transparent)`, color: c }}>{surname(l)[0]}</span>
                  <span className="font-semibold text-sm leading-tight">{l.name}</span>
                </span>
                <span className="text-sm font-semibold" style={{ color: c }}>{l.decision?.label ?? l.word}</span>
                <span className="num mute text-[11px]">{pass} of {known} checks passed</span>
                <span className="text-[11px]" style={{ color: "var(--blue)" }}>{on ? "Hide the analysis" : "See the full analysis"}</span>
              </button>
            </li>
          );
        })}
      </ul>
      {chosen && <PanellistCard l={chosen} wide />}
    </div>
  );
}

/** All the panellist cards in a grid. */
export function InvestorCards({ lenses }: { lenses: Lens[] }) {
  return (
    <section className="grid gap-3" aria-label="The panellists">
      <div>
        <h3 className="text-lg font-semibold m-0">The panellists</h3>
        <p className="mute text-sm m-0 mt-1 max-w-3xl">What each investor analysed, what they look for in a stock, what they found here, and their call.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {lenses.map((l) => <PanellistCard key={l.key} l={l} />)}
      </div>
    </section>
  );
}

export function PanellistCard({ l, wide = false }: { l: Lens; wide?: boolean }) {
  const color = l.decision ? CALL_COLOR[l.decision.call] : STANCE_COLOR[stanceOf(l.fit)], { pass, known } = counts(l);
  const by = (r: Check["result"]) => l.checks.filter((k) => k.result === r);
  const reading = firstSentence(l.narrative);
  const watch = firstSentence(l.ahead);
  const found = [...by("pass").slice(0, 3), ...by("fail").slice(0, 3), ...by("partial").slice(0, 2)];
  return (
    <article id={`panellist-${l.key}`} className={`card p-5 grid gap-4 content-start ${wide ? "md:grid-cols-2 md:gap-x-8" : ""}`} style={{ borderTop: `3px solid ${color}` }}>
      <header className={`grid gap-2 ${wide ? "md:col-span-2" : ""}`}>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <span className="flex items-center gap-2 min-w-0">
            <span aria-hidden className="inline-grid place-items-center w-8 h-8 rounded-full text-sm font-bold shrink-0"
              style={{ background: `color-mix(in srgb, ${color} 20%, transparent)`, color }}>{surname(l)[0]}</span>
            <span className="font-semibold leading-tight">{l.name}</span>
          </span>
          <CallChip l={l} big={wide} />
        </div>
        <p className="m-0 text-sm mute">Asks: {l.question}</p>
        {l.fit != null && (
          <div className="flex items-center gap-2">
            <div className="h-1.5 flex-1 rounded-full overflow-hidden" style={{ background: "var(--line)" }}>
              <div style={{ width: `${Math.round(l.fit * 100)}%`, height: "100%", background: color }} />
            </div>
            <span className="num text-xs mute shrink-0">{pass} of {known} checks passed</span>
          </div>
        )}
        {l.note && <p className="m-0 text-xs"><b>Looks like a {l.note.category.toLowerCase()}:</b> <span className="mute">{l.note.why}</span></p>}
      </header>

      <div className="grid gap-4 content-start">
        {l.decision && (
          <Block title="Final call">
            <p className="m-0 text-sm"><b style={{ color }}>{l.decision.label}.</b> {l.decision.why}</p>
          </Block>
        )}
        {reading && <Block title="The reading"><p className="m-0 text-sm leading-relaxed">{reading}</p></Block>}
        {(l.looks_for?.length ?? 0) > 0 && (
          <Block title="Looks for">
            <ul className="m-0 p-0 list-none grid gap-1 text-sm">
              {l.looks_for!.map((x) => <li key={x} className="flex gap-2"><span aria-hidden className="mute shrink-0">•</span><span>{x}</span></li>)}
            </ul>
          </Block>
        )}
      </div>

      <div className="grid gap-4 content-start">
        <Block title={wide ? "What they checked, and what they found" : "What they found"}>
          <ul className="m-0 p-0 list-none grid gap-1.5 text-sm">
            {(wide ? l.checks : found).map((k) => (
              <li key={k.id} className="flex gap-2 items-start">
                <span aria-hidden className="font-bold shrink-0 w-3 text-center" style={{ color: MARK[k.result].color }}>{MARK[k.result].mark}</span>
                <span><span className="font-medium">{checkLabel(k)}</span> <span className="num mute text-xs">{cut(k.shown, wide ? 160 : 90)}</span>
                  {wide && <span className="block mute text-[11px]">Idea: {k.principle}. <i>{k.source}</i></span>}</span>
              </li>
            ))}
            {known === 0 && <li className="mute">Not enough data to test.</li>}
          </ul>
        </Block>
        {wide && l.narrative && <Block title="Their view in full"><p className="m-0 text-sm leading-relaxed">{l.narrative}</p></Block>}
        {watch && <Block title="Watches next"><p className="m-0 text-sm leading-relaxed">{wide && l.ahead ? l.ahead : watch}</p></Block>}
      </div>

      <footer className={`mute text-[11px] flex flex-wrap gap-x-3 gap-y-1 ${wide ? "md:col-span-2" : ""}`}>
        {l.book && <span>From {l.book}</span>}
        <span>{l.backtested ? "Back-tested against what happened next" : "Not back-tested"}</span>
        {l.caveat && <span>{l.caveat}</span>}
        <span>A reading of the evidence by this investor's rules, not personal advice.</span>
      </footer>
    </article>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <span className="text-xs font-semibold" style={{ color: "var(--text)" }}>{title}</span>
      {children}
    </div>
  );
}
