import { useEffect, useId, useRef, useState } from "react";
import { LEVELS, LEVEL_KEYS, setLevel, useLevel } from "../literacy";

/** The top-right control: shows the current level and lets the reader change it or retake the quiz at any time. */
export function LevelSwitch({ onQuiz }: { onQuiz: () => void }) {
  const level = useLevel();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); root.current?.querySelector("button")?.focus(); } };
    document.addEventListener("pointerdown", away); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [open]);

  const label = level ? LEVELS[level].name : "Set level";
  return (
    <div ref={root} className="relative shrink-0">
      <button type="button" className="btn ghost sm" aria-haspopup="true" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}
        title="How much finance jargon the site uses">
        <span className="mute hidden sm:inline">Level</span> <b>{label}</b> <span aria-hidden className="text-xs">▾</span>
      </button>
      {open && (
        <div id={id} role="group" aria-label="Your finance level" className="card absolute right-0 mt-1 p-2 grid gap-1" style={{ width: "min(320px, calc(100vw - 24px))", zIndex: "var(--z-dropdown)", boxShadow: "0 8px 24px color-mix(in srgb, #000 35%, transparent)" }}>
          <span className="text-xs mute px-2 pt-1">How much finance jargon should the site use?</span>
          {LEVEL_KEYS.map((k) => (
            <button key={k} type="button" aria-pressed={level === k} onClick={() => { setLevel(k); setOpen(false); }}
              className="text-left rounded-lg px-2 py-2 grid gap-0 cursor-pointer border-0" style={{ minHeight: 44, background: level === k ? "var(--card-alt)" : "transparent", color: "var(--foreground)" }}>
              <span className="text-sm font-semibold">{level === k ? "✓ " : ""}{LEVELS[k].name}</span>
              <span className="text-xs mute">{LEVELS[k].short}</span>
            </button>
          ))}
          <button type="button" className="btn ghost sm justify-self-start mt-1" onClick={() => { setOpen(false); onQuiz(); }}>Retake the quiz</button>
        </div>
      )}
    </div>
  );
}
