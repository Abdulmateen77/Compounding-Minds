import { useEffect, useMemo, useRef, useState } from "react";
import { LEVELS, LEVEL_KEYS, QUIZ, levelForScore, setLevel, type Level } from "../literacy";
import { Say } from "./Say";

/* The onboarding quiz: six multiple-choice questions, easiest first, that set how much explaining the whole site does. It opens
   by itself on a first visit and again from the level control in the top bar. Skipping keeps the middle level. */

const NOT_SURE = "I'm not sure";
const shuffle = <T,>(xs: T[]) => xs.map((x) => [Math.random(), x] as const).sort((a, b) => a[0] - b[0]).map((p) => p[1]);
const SAMPLE = "Return on capital is 18% and debt to EBITDA is 1.4×, so free cash flow covers the dividend.";

export function LevelQuiz({ onClose }: { onClose: () => void }) {
  // Each question's options in a fresh order, so the right answer is not always in the same place.
  const order = useMemo(() => QUIZ.map((q) => shuffle(q.options.map((_, i) => i))), []);
  const [step, setStep] = useState(0);
  const [picked, setPicked] = useState<(number | null)[]>(() => QUIZ.map(() => null));   // original option index; -1 = not sure
  const [result, setResult] = useState<Level | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const back = useRef<Element | null>(null);

  useEffect(() => {
    back.current = document.activeElement;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; (back.current as HTMLElement | null)?.focus?.(); };
  }, []);
  useEffect(() => { box.current?.querySelector<HTMLElement>("[data-first]")?.focus(); }, [step, result]);

  const score = picked.reduce<number>((n, p, i) => n + (p === QUIZ[i].answer ? 1 : 0), 0);
  const skip = () => { setLevel("intermediate"); onClose(); };
  const finish = (l: Level) => { setLevel(l); onClose(); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { e.stopPropagation(); result ? onClose() : skip(); return; }
    if (e.key !== "Tab") return;
    const f = [...(box.current?.querySelectorAll<HTMLElement>("button:not(:disabled), [tabindex='0']") ?? [])];
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  const q = QUIZ[step];
  const choose = (i: number) => setPicked((p) => p.map((x, k) => (k === step ? i : x)));

  return (
    <div className="fixed inset-0 grid place-items-center p-3 overflow-y-auto" style={{ zIndex: "var(--z-modal)", background: "color-mix(in srgb, #000 62%, transparent)" }} onKeyDown={onKey}>
      <div ref={box} role="dialog" aria-modal="true" aria-labelledby="quiz-title" className="card w-full max-w-lg p-5 md:p-6 grid gap-4" style={{ maxHeight: "calc(100dvh - 24px)", overflowY: "auto" }}>
        {!result ? (
          <>
            <div className="grid gap-1">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs mute">Quick setup · question {step + 1} of {QUIZ.length}</span>
                <button type="button" className="bg-transparent border-0 p-0 text-xs underline underline-offset-4 cursor-pointer" style={{ color: "var(--muted)" }} onClick={skip}>Skip for now</button>
              </div>
              <div className="h-1 rounded-full overflow-hidden" style={{ background: "var(--divider)" }} aria-hidden>
                <div style={{ width: `${((step + 1) / QUIZ.length) * 100}%`, height: "100%", background: "var(--primary-solid)", transition: "width var(--duration-slow) var(--ease-soft)" }} />
              </div>
            </div>
            {step === 0 && <p className="m-0 text-sm mute">How much do you know about finance? Six quick questions set how much explaining this site does. “I'm not sure” is a fine answer, and you can change it any time from the top right.</p>}
            <h2 id="quiz-title" className="text-lg font-semibold m-0">{q.q}</h2>
            <div role="radiogroup" aria-labelledby="quiz-title" className="grid gap-2">
              {[...order[step], -1].map((i, k) => {
                const on = picked[step] === i;
                return (
                  <button key={i} type="button" role="radio" aria-checked={on} data-first={k === 0 ? "" : undefined} onClick={() => choose(i)}
                    className="card text-left px-3 py-3 text-sm cursor-pointer flex items-start gap-3"
                    style={{ minHeight: 44, color: i === -1 ? "var(--muted)" : "var(--foreground)", borderColor: on ? "var(--primary)" : undefined, boxShadow: on ? "0 0 0 2px var(--primary)" : undefined }}>
                    <span aria-hidden className="inline-block w-4 h-4 rounded-full shrink-0 mt-0.5" style={{ border: "2px solid var(--muted)", background: on ? "var(--primary-solid)" : "transparent", borderColor: on ? "var(--primary)" : undefined }} />
                    <span>{i === -1 ? NOT_SURE : q.options[i]}</span>
                  </button>
                );
              })}
            </div>
            <div className="flex justify-between gap-2">
              <button type="button" className="btn ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</button>
              <button type="button" className="btn" disabled={picked[step] == null}
                onClick={() => (step < QUIZ.length - 1 ? setStep(step + 1) : setResult(levelForScore(score)))}>{step < QUIZ.length - 1 ? "Next" : "See my level"}</button>
            </div>
          </>
        ) : (
          <Result level={result} score={score} onPick={setResult} onStart={() => finish(result)} />
        )}
      </div>
    </div>
  );
}

function Result({ level, score, onPick, onStart }: { level: Level; score: number; onPick: (l: Level) => void; onStart: () => void }) {
  const L = LEVELS[level];
  return (
    <>
      <div className="grid gap-1">
        <span className="text-xs mute">{score} of {QUIZ.length} right</span>
        <h2 id="quiz-title" className="text-xl font-semibold m-0">You're set up as {L.name}</h2>
        <p className="m-0 text-sm mute">{L.short}</p>
      </div>
      <ul className="m-0 pl-5 grid gap-1 text-sm list-disc">{L.changes.map((c) => <li key={c}>{c}</li>)}</ul>
      <div className="rounded-xl p-3 grid gap-1" style={{ background: "var(--card-alt)" }}>
        <span className="text-xs mute">How a sentence will read for you</span>
        <span className="text-sm leading-relaxed"><Say level={level}>{SAMPLE}</Say></span>
      </div>
      <div className="grid gap-1">
        <span className="text-xs mute" id="quiz-other">Not right? Choose another level</span>
        <div role="radiogroup" aria-labelledby="quiz-other" className="flex gap-2 flex-wrap">
          {LEVEL_KEYS.map((k) => (
            <button key={k} type="button" role="radio" aria-checked={k === level} className="chip cursor-pointer bg-transparent" style={{ minHeight: 32, color: k === level ? "var(--foreground)" : undefined, borderColor: k === level ? "var(--primary)" : undefined }} onClick={() => onPick(k)}>{LEVELS[k].name}</button>
          ))}
        </div>
      </div>
      <div className="flex justify-end"><button type="button" data-first className="btn" onClick={onStart}>Start exploring</button></div>
    </>
  );
}
