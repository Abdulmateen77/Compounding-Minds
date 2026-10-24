import { useEffect, useRef, useState } from "react";
import { STANCE_COLOR } from "../api/client";
import { askInvestor, type ChatMsg } from "../chat";
import type { Lens } from "../research";
import { MARK, stanceOf, surname } from "./lenses";

/* A one-on-one chat with the selected investor, plus their checks. Used inside the animation (a panel beside the stage, a bottom
   sheet on small screens) and on its own in the 2D fallback. The answers come from research/chat.py, which answers only from this
   investor's checks in the report. */

const ASKS = ["Why did you give this reading?", "Which check hurt most?", "What would change your mind?", "What did pass?"];

type Props = {
  cik: number;
  lens: Lens;
  messages: ChatMsg[];
  setMessages: (f: (m: ChatMsg[]) => ChatMsg[]) => void;
  onClose: () => void;
  big?: boolean;
  inline?: boolean;                 // a normal block instead of an overlay on the stage
  onBusy?: (busy: boolean) => void; // the investor is composing an answer
  onReply?: () => void;             // an answer just arrived
};

export default function InvestorPanel({ cik, lens, messages, setMessages, onClose, big, inline, onBusy, onReply }: Props) {
  const [tab, setTab] = useState<"chat" | "checks">("chat");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const lastAnswer = useRef<HTMLDivElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const color = STANCE_COLOR[stanceOf(lens.fit)];
  const first = lens.name.split(" ")[0];
  const text = big ? "text-sm" : "text-xs";

  useEffect(() => { input.current?.focus({ preventScroll: true }); }, [lens.key]);
  useEffect(() => { setErr(null); setDraft(""); }, [lens.key]);
  // A new answer scrolls to its own first line, so it is read from the start rather than from the end.
  useEffect(() => {
    const m = messages[messages.length - 1];
    (m?.role === "assistant" ? lastAnswer : end).current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [messages.length, busy, tab]);
  useEffect(() => () => onBusy?.(false), [onBusy]);

  const send = async (q: string) => {
    q = q.trim();
    if (!q || busy) return;
    const history = messages;
    setMessages((m) => [...m, { role: "user", content: q }]);
    setDraft(""); setBusy(true); setErr(null); onBusy?.(true);
    try {
      const out = await askInvestor(cik, lens.key, q, history);
      setMessages((m) => [...m, { role: "assistant", content: out.answer, source: out.source }]);
      onReply?.();
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(false); onBusy?.(false);
      input.current?.focus({ preventScroll: true });
    }
  };

  // The stage behind this panel listens for arrow keys, space and drags: typing here must not move the camera.
  const quiet = {
    onKeyDown: (e: React.KeyboardEvent) => { e.stopPropagation(); if (e.key === "Escape") onClose(); },
    onPointerDown: (e: React.PointerEvent) => e.stopPropagation(),
  };
  const asked = new Set(messages.filter((m) => m.role === "user").map((m) => m.content));
  const follow = ASKS.filter((q) => !asked.has(q)).slice(0, 3);
  const lastAssistant = messages.map((m) => m.role).lastIndexOf("assistant");

  const frame = inline
    ? "flex flex-col rounded-xl overflow-hidden"
    : `absolute inset-x-2 bottom-2 top-14 sm:inset-x-auto sm:right-3 sm:top-3 sm:bottom-3 ${big ? "sm:w-[400px]" : "sm:w-[330px]"} flex flex-col rounded-xl overflow-hidden`;

  return (
    <aside {...quiet} role="dialog" aria-modal="false" aria-label={`Talk to ${lens.name}`} className={frame}
      style={{ background: "var(--panel)", border: `2px solid ${color}`, color: "var(--text)", ...(inline ? { minHeight: 420, maxHeight: 560 } : {}) }}>
      <div className="flex items-start justify-between gap-2 p-3" style={{ borderBottom: "1px solid var(--line)" }}>
        <div>
          <b className={big ? "text-base" : "text-sm"}>{lens.name}</b>
          <div className="text-xs font-medium" style={{ color }}>{lens.word}</div>
        </div>
        <div className="flex items-center gap-1">
          {messages.length > 0 && <button className="btn ghost" style={{ padding: ".35rem .7rem", fontSize: ".75rem" }} onClick={() => { setMessages(() => []); setErr(null); }}>Clear</button>}
          <button className="btn ghost" style={{ padding: ".35rem .8rem", minWidth: 44, minHeight: 36 }} onClick={onClose} aria-label={`Close the chat with ${lens.name}${inline ? "" : " and resume the animation"}`}>×</button>
        </div>
      </div>

      <div className="flex gap-1 px-3 pt-2" role="tablist" aria-label="Chat or checks">
        {(["chat", "checks"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className="chip cursor-pointer"
            style={{ minHeight: 32, ...(tab === t ? { color: "var(--text)", borderColor: "var(--blue)" } : {}) }}>{t === "chat" ? `Ask ${first}` : `Their checks (${lens.checks.length})`}</button>
        ))}
      </div>

      {tab === "chat" ? (
        <>
          <div className={`flex-1 overflow-auto p-3 grid gap-2 content-start ${text}`} role="log" aria-live="polite" aria-relevant="additions" aria-busy={busy}>
            {messages.length === 0 && (
              <div className="grid gap-2">
                <p className="m-0 mute" style={{ lineHeight: 1.45 }}>Ask {first} why they reached this reading. They answer from their own checks on this company, and say so when something isn't in them.</p>
                {ASKS.slice(0, 3).map((q) => <button key={q} className="btn ghost text-left" style={{ padding: ".55rem .8rem", fontSize: "inherit" }} onClick={() => send(q)}>{q}</button>)}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} ref={i === lastAssistant ? lastAnswer : undefined} className={m.role === "user" ? "justify-self-end" : "justify-self-start"} style={{ maxWidth: "92%", scrollMarginTop: 8 }}>
                <div className="sr-only">{m.role === "user" ? "You asked:" : `${first} answered:`}</div>
                <div className="rounded-xl px-3 py-2" style={{ lineHeight: 1.45, background: m.role === "user" ? "var(--blue)" : "var(--panel2)", color: m.role === "user" ? "#fff" : "var(--text)" }}>{m.content}</div>
                {m.role === "assistant" && <div className="mute text-[11px] mt-0.5">{m.source === "rules" ? "Read straight from their checks" : "AI portrayal, from their checks"}</div>}
              </div>
            ))}
            {busy && <div className="mute justify-self-start flex items-center gap-2"><span className="inline-flex gap-1" aria-hidden>{[0, 1, 2].map((d) => <span key={d} className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--mute)", animation: `dots 1s ${d * 0.15}s infinite` }} />)}</span>{first} is thinking…</div>}
            {err && <div role="alert" className="rounded-lg p-2" style={{ border: "1px solid var(--red)", color: "var(--red)" }}>Could not get an answer: {err} <button className="underline bg-transparent border-0 cursor-pointer" style={{ color: "inherit" }} onClick={() => { const q = [...messages].reverse().find((m) => m.role === "user"); if (q) { setMessages((m) => m.slice(0, -1)); void send(q.content); } }}>Try again</button></div>}
            <div ref={end} />
          </div>
          {messages.length > 0 && !busy && follow.length > 0 && (
            <div className="px-3 pb-2 flex gap-1.5 flex-wrap" role="group" aria-label="Suggested follow-up questions">
              {follow.map((q) => <button key={q} className="chip cursor-pointer" style={{ minHeight: 30, color: "var(--text)" }} onClick={() => send(q)}>{q}</button>)}
            </div>
          )}
          <form onSubmit={(e) => { e.preventDefault(); void send(draft); }} className="p-3 grid gap-1.5" style={{ borderTop: "1px solid var(--line)" }}>
            <div className="flex gap-2">
              <input ref={input} value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={400} disabled={busy} placeholder={`Ask ${first} a question`}
                aria-label={`Question for ${lens.name}`} enterKeyHint="send" autoComplete="off"
                className="card flex-1 min-w-0 px-3 py-2 outline-none focus:border-[var(--blue)]" style={{ color: "var(--text)", fontSize: big ? "1rem" : ".85rem", minHeight: 44 }} />
              <button className="btn" style={{ padding: ".4rem 1rem", minHeight: 44 }} disabled={busy || !draft.trim()}>Send</button>
            </div>
            <p className="m-0 mute text-[11px]" style={{ lineHeight: 1.35 }}>An AI portrayal built from {surname(lens)}'s published principles and the checks in this report. Not the real person. Research, not advice.</p>
          </form>
        </>
      ) : (
        <div className={`flex-1 overflow-auto p-3 ${text}`}>
          <p className="mute m-0 mb-2">{lens.question}</p>
          {lens.narrative && <p className="m-0 mb-3" style={{ lineHeight: 1.45 }}>{lens.narrative}</p>}
          <ul className="m-0 p-0 list-none grid gap-2">
            {lens.checks.map((k) => (
              <li key={k.id} className="flex gap-2 items-start">
                <span aria-label={k.result} className="inline-grid place-items-center w-5 h-5 rounded-full shrink-0" style={{ background: `color-mix(in srgb, ${MARK[k.result].color} 20%, transparent)`, color: MARK[k.result].color }}>{MARK[k.result].mark}</span>
                <span><span className="font-medium">{k.check}</span> <span className="num mute">{k.shown}</span></span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}
