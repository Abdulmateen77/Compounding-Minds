import { useEffect, useRef } from "react";
import { LEVELS, LEVEL_KEYS, setLevel } from "../literacy";

/* The one-question onboarding: how much does the reader know about investing? It opens by itself on a first visit and sets how much
   explaining the whole site does. Closing it without choosing keeps the middle level. The top-bar Level control changes it later. */

export function LevelPicker({ onClose }: { onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const back = document.activeElement as HTMLElement | null;
    document.body.style.overflow = "hidden";
    box.current?.querySelector<HTMLElement>("button")?.focus();
    return () => { document.body.style.overflow = ""; back?.focus?.(); };
  }, []);

  const choose = (l: (typeof LEVEL_KEYS)[number]) => { setLevel(l); onClose(); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.stopPropagation(); choose("intermediate"); return; }
    if (e.key !== "Tab") return;
    const f = [...(box.current?.querySelectorAll<HTMLElement>("button") ?? [])];
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  return (
    <div className="fixed inset-0 grid place-items-center p-3 overflow-y-auto" style={{ zIndex: "var(--z-modal)", background: "color-mix(in srgb, #000 62%, transparent)" }} onKeyDown={onKey}>
      <div ref={box} role="dialog" aria-modal="true" aria-labelledby="level-title" className="card w-full max-w-md p-5 md:p-6 grid gap-4" style={{ maxHeight: "calc(100dvh - 24px)", overflowY: "auto" }}>
        <div className="grid gap-1">
          <h2 id="level-title" className="text-lg font-semibold m-0">Are you a beginner, intermediate or advanced?</h2>
          <p className="m-0 text-sm mute">With investing and finance. It sets how much the site explains, and you can change it any time from the top right.</p>
        </div>
        <div className="grid gap-2">
          {LEVEL_KEYS.map((k) => (
            <button key={k} type="button" onClick={() => choose(k)} className="card text-left px-4 py-3 cursor-pointer grid gap-0" style={{ minHeight: 56, color: "var(--foreground)" }}>
              <span className="text-base font-semibold">{LEVELS[k].name}</span>
              <span className="text-sm mute">{LEVELS[k].short}</span>
            </button>
          ))}
        </div>
        <div className="flex justify-end">
          <button type="button" className="bg-transparent border-0 p-0 text-xs underline underline-offset-4 cursor-pointer" style={{ color: "var(--muted)" }} onClick={() => choose("intermediate")}>Skip for now</button>
        </div>
      </div>
    </div>
  );
}
