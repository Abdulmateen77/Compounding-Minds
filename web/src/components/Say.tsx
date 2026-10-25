import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { glossify, useEffectiveLevel, type Level } from "../literacy";

/* Text that knows who is reading it. `Say` puts a dotted underline under finance terms (what gets one depends on the level) and a
   tap, hover or focus shows the plain definition. `Guide` is a strip written for beginners only; `Detail` is for advanced readers. */

function Term({ term, def }: { term: string; def: string }) {
  const [pos, setPos] = useState<{ x: number; y: number; below: boolean } | null>(null);
  const ref = useRef<HTMLSpanElement>(null);
  const id = useId();
  const show = () => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const w = Math.min(280, window.innerWidth - 16);
    setPos({ x: Math.max(8, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - 8)), y: r.top > 130 ? r.top - 6 : r.bottom + 6, below: r.top <= 130 });
  };
  const hide = () => setPos(null);
  useEffect(() => {
    if (!pos) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") hide(); };
    const away = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) hide(); };
    window.addEventListener("keydown", esc); window.addEventListener("scroll", hide, true); window.addEventListener("resize", hide); window.addEventListener("pointerdown", away);
    return () => { window.removeEventListener("keydown", esc); window.removeEventListener("scroll", hide, true); window.removeEventListener("resize", hide); window.removeEventListener("pointerdown", away); };
  }, [pos]);
  return (
    <>
      <span ref={ref} className="term" role="button" tabIndex={0} aria-describedby={pos ? id : undefined} aria-expanded={!!pos}
        onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}
        onClick={(e) => { e.stopPropagation(); pos ? hide() : show(); }}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pos ? hide() : show(); } }}>{term}</span>
      {pos && createPortal(
        <span id={id} role="tooltip" className="term-pop" style={{ left: pos.x, top: pos.y, transform: pos.below ? undefined : "translateY(-100%)" }}>{def}</span>,
        document.body)}
    </>
  );
}

/** A string with its finance terms explained for this reader. Pass `level` only to override the reader's own (the quiz preview does). */
export function Say({ children, level }: { children?: string | null; level?: Level }) {
  const mine = useEffectiveLevel();
  if (!children) return null;
  const segs = glossify(children, level ?? mine);
  if (segs.length === 1 && typeof segs[0] === "string") return <>{children}</>;
  return <>{segs.map((s, i) => (typeof s === "string" ? s : <Term key={i} term={s.term} def={s.def} />))}</>;
}

/** Wrap a ReactNode that may be a plain string (a `blurb` prop) so strings are explained and elements pass through. */
export const sayNode = (n: ReactNode): ReactNode => (typeof n === "string" ? <Say>{n}</Say> : n);

/** A short guide for beginners: what this page or section is for, in everyday words. Nothing is shown to other readers. */
export function Guide({ children, title = "In plain words" }: { children: ReactNode; title?: string }) {
  const level = useEffectiveLevel();
  if (level !== "beginner") return null;
  return (
    <aside className="guide" aria-label={title}>
      <b>{title}</b>
      <span>{typeof children === "string" ? <Say>{children}</Say> : children}</span>
    </aside>
  );
}

/** Content for readers at these levels only. */
export function OnlyFor({ levels, children }: { levels: Level[]; children: ReactNode }) {
  const level = useEffectiveLevel();
  return levels.includes(level) ? <>{children}</> : null;
}
