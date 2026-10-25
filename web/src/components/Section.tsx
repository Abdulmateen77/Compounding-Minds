import { useId, useState, type ReactNode } from "react";

/* Shared building blocks for keeping a page short: a section heading with one sentence under it, an optional "how this works" toggle
   for the longer explanation, and a collapsible block whose closed state still says something useful. */

/** An h2 with a one-line blurb. Anything longer goes in `more`, behind a small toggle, so it is there when wanted and silent otherwise. */
export function Head({ title, blurb, more, right }: { title: string; blurb?: ReactNode; more?: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-3 flex-wrap">
      <div className="grid gap-1 min-w-0">
        <h2 className="text-xl font-semibold m-0">{title}</h2>
        {blurb && <p className="mute text-sm m-0 max-w-3xl">{blurb}</p>}
        {more && <Explain>{more}</Explain>}
      </div>
      {right}
    </div>
  );
}

/** "How this works": a small toggle that reveals the longer explanation. */
export function Explain({ children, label = "How this works" }: { children: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className="text-xs">
      <button type="button" className="bg-transparent border-0 p-0 cursor-pointer underline underline-offset-4" style={{ color: "var(--blue)" }}
        aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>{open ? "Hide" : label}</button>
      {open && <div id={id} className="mute leading-relaxed mt-1 max-w-3xl grid gap-1">{children}</div>}
    </div>
  );
}

/** A card that opens and closes. `summary` stays visible when it is closed (a headline figure or two), so closed never means blank. */
export function Disclosure({ title, summary, count, defaultOpen = false, level = 2, children }: {
  title: ReactNode; summary?: ReactNode; count?: ReactNode; defaultOpen?: boolean; level?: 2 | 3; children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  const H = level === 2 ? "h2" : "h3";
  return (
    <section className="card">
      <H className="m-0">
        <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}
          className="w-full text-left bg-transparent border-0 cursor-pointer p-4 md:px-5 flex items-start gap-3" style={{ color: "var(--text)" }}>
          <span aria-hidden className="mute mt-1 inline-block w-3 shrink-0 text-xs" style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform .15s" }}>▶</span>
          <span className="grid gap-1 min-w-0 flex-1">
            <span className="flex items-baseline gap-2 flex-wrap">
              <span className={level === 2 ? "text-lg font-semibold" : "text-base font-semibold"}>{title}</span>
              {count && <span className="chip">{count}</span>}
            </span>
            {summary && !open && <span className="mute text-sm font-normal leading-snug">{summary}</span>}
          </span>
        </button>
      </H>
      {open && <div id={id} className="px-4 md:px-5 pb-5 grid gap-3 grid-cols-[minmax(0,1fr)]">{children}</div>}
    </section>
  );
}
