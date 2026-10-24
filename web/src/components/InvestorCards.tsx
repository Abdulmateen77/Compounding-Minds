import { STANCE_COLOR } from "../api/client";
import type { Check, Lens } from "../research";
import { MARK, checkLabel, counts, cut, stanceOf, surname } from "../scene/lenses";

/** One card per panellist: their reading, what they look for, what they found (strengths and concerns, each with its number),
    and what they would watch next. Everything comes from the report: the checks, the investor's guide and the written view. */
export function InvestorCards({ lenses }: { lenses: Lens[] }) {
  return (
    <section className="grid gap-3" aria-label="The panellists">
      <div>
        <h3 className="text-lg font-semibold m-0">The panellists</h3>
        <p className="mute text-sm m-0 mt-1 max-w-3xl">What each investor analysed, what they look for in a stock, and what they found here.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {lenses.map((l) => <Card key={l.key} l={l} />)}
      </div>
    </section>
  );
}

const firstSentence = (text?: string | null) => {
  const t = text?.trim();
  if (!t) return null;
  // a sentence ends at . ! or ? followed by a space and a capital letter (so "25.5%" and "3.8x" never cut it short)
  const s = t.match(/^[\s\S]+?[.!?](?=\s+[A-Z“"]|\s*$)/)?.[0] ?? t;
  return cut(s.trim(), 220);
};

function Card({ l }: { l: Lens }) {
  const color = STANCE_COLOR[stanceOf(l.fit)], { pass, known } = counts(l);
  const by = (r: Check["result"]) => l.checks.filter((k) => k.result === r);
  const reading = firstSentence(l.narrative);
  const watch = firstSentence(l.ahead);
  return (
    <article id={`panellist-${l.key}`} className="card p-5 grid gap-4 content-start" style={{ borderTop: `3px solid ${color}` }}>
      <header className="grid gap-2">
        <div className="flex items-center justify-between gap-3">
          <span className="flex items-center gap-2 min-w-0">
            <span aria-hidden className="inline-grid place-items-center w-8 h-8 rounded-full text-sm font-bold shrink-0"
              style={{ background: `color-mix(in srgb, ${color} 20%, transparent)`, color }}>{surname(l)[0]}</span>
            <span className="font-semibold leading-tight">{l.name}</span>
          </span>
          <span className="chip shrink-0" style={{ color, borderColor: color }}>{l.word}</span>
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

      {reading && <Block title="The reading"><p className="m-0 text-sm leading-relaxed">{reading}</p></Block>}

      {(l.looks_for?.length ?? 0) > 0 && (
        <Block title="Looks for">
          <ul className="m-0 p-0 list-none grid gap-1 text-sm">
            {l.looks_for!.map((x) => <li key={x} className="flex gap-2"><span aria-hidden className="mute shrink-0">•</span><span>{x}</span></li>)}
          </ul>
        </Block>
      )}

      <Block title="What they found">
        <ul className="m-0 p-0 list-none grid gap-1.5 text-sm">
          {[...by("pass").slice(0, 3), ...by("fail").slice(0, 3), ...by("partial").slice(0, 2)].map((k) => (
            <li key={k.id} className="flex gap-2 items-start">
              <span aria-hidden className="font-bold shrink-0 w-3 text-center" style={{ color: MARK[k.result].color }}>{MARK[k.result].mark}</span>
              <span><span className="font-medium">{checkLabel(k)}</span> <span className="num mute text-xs">{cut(k.shown, 90)}</span></span>
            </li>
          ))}
          {known === 0 && <li className="mute">Not enough data to test.</li>}
        </ul>
      </Block>

      {watch && <Block title="Watches next"><p className="m-0 text-sm leading-relaxed">{watch}</p></Block>}

      <footer className="mute text-[11px] flex flex-wrap gap-x-3 gap-y-1">
        {l.book && <span>From {l.book}</span>}
        <span>{l.backtested ? "Back-tested against what happened next" : "Not back-tested"}</span>
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
