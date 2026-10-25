import { useEffect, useMemo, useRef, useState } from "react";
import { CALL_COLOR, TONE, type Analysis, type Lens } from "../research";
import { checkLabel, cut, pickFaceOffs, surname } from "../scene/lenses";
import { speak, stopSpeaking, useVoiceStatus } from "../voice";

/* The debate as a chat log. Every line comes from the report: each investor's reading and call, the face-offs picked from their
   own checks (a case, an objection, the judge's ruling), and the panel's verdict. Nothing is invented for the debate. */

type Msg = { kind: "moderator" | "investor" | "heading" | "verdict"; who?: number; role?: "opening" | "case" | "objection" | "ruling"; text: string; detail?: string };

const firstSentence = (text?: string | null) => {
  const t = text?.trim();
  if (!t) return null;
  const s = t.match(/^[\s\S]+?[.!?](?=\s+[A-Z“"]|\s*$)/)?.[0] ?? t;
  return cut(s.trim(), 240);
};

function script(a: Analysis, company: string): Msg[] {
  const L = a.lenses, out: Msg[] = [];
  out.push({ kind: "moderator", text: `The question for the panel: is ${company} worth investing in? ${L.length} investors, each judging by their own rules and the company's filings.` });
  out.push({ kind: "heading", text: "Opening statements" });
  L.forEach((l, i) => {
    const reading = firstSentence(l.narrative) ?? `${l.word} on my checks.`;
    out.push({ kind: "investor", who: i, role: "opening", text: reading, detail: l.decision ? `Call: ${l.decision.label}. ${l.decision.why}` : undefined });
  });
  const faceoffs = pickFaceOffs(L);
  if (!faceoffs.length) out.push({ kind: "moderator", text: "They read it much the same way, so there is no face-off." });
  faceoffs.forEach((f, k) => {
    out.push({ kind: "heading", text: `Face-off${faceoffs.length > 1 ? ` ${k + 1} of ${faceoffs.length}` : ""}: ${surname(L[f.pair[0]])} vs ${surname(L[f.pair[1]])}` });
    f.turns.forEach((t) => {
      const q = t.quote;
      if (t.role === "ruling") {
        out.push({ kind: "investor", who: t.by, role: "ruling", text: t.headline ?? "My ruling.", detail: `${q.head}: ${q.shown}. ${q.idea}.` });
      } else {
        const lead = t.role === "objection" ? `${surname(L[t.to])}, look at this. ` : "";
        out.push({ kind: "investor", who: t.by, role: t.role, text: `${lead}${q.head}: ${q.shown}.`, detail: q.idea });
      }
    });
  });
  out.push({ kind: "heading", text: "Final verdict" });
  out.push({ kind: "verdict", text: a.panel?.headline ?? a.overall.headline, detail: `${a.overall.headline}. ${a.overall.why}` });
  return out;
}

const spoken = (m: Msg) => [m.text, m.detail && m.role !== "case" && m.role !== "objection" ? m.detail : ""].filter(Boolean).join(" ");
const pause = (m: Msg) => (m.kind === "heading" ? 700 : Math.min(4200, 1100 + (m.text.length + (m.detail?.length ?? 0)) * 18));

export function DebateLog({ a, company }: { a: Analysis; company: string }) {
  const msgs = useMemo(() => script(a, company), [a, company]);
  const voice = useVoiceStatus();
  const [shown, setShown] = useState(0);              // how many lines are visible
  const [running, setRunning] = useState(false);
  const [useVoice, setUseVoice] = useState(false);
  const [typing, setTyping] = useState(false);
  const bottom = useRef<HTMLDivElement | null>(null);
  const stop = useRef<AbortController | null>(null);
  const done = shown >= msgs.length;

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [shown, typing]);
  useEffect(() => () => { stop.current?.abort(); stopSpeaking(); }, []);
  // a link with "debate=play" starts the debate on arrival (for showing it to a room)
  useEffect(() => { if (/[?&]debate=play/.test(window.location.href)) start(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  async function run(from: number) {
    stop.current?.abort();
    const ctl = new AbortController();
    stop.current = ctl;
    setRunning(true);
    for (let i = from; i < msgs.length && !ctl.signal.aborted; i++) {
      setTyping(msgs[i].kind === "investor");
      await new Promise((r) => setTimeout(r, msgs[i].kind === "investor" ? 650 : 250));
      if (ctl.signal.aborted) break;
      setTyping(false);
      setShown(i + 1);
      const m = msgs[i];
      if (useVoice && voice.data?.enabled && m.kind !== "heading") {
        const who = m.kind === "investor" && m.who != null ? a.lenses[m.who].key : "judge";
        try { await speak(who, spoken(m), ctl.signal); } catch { await new Promise((r) => setTimeout(r, pause(m))); }
      } else {
        await new Promise((r) => setTimeout(r, pause(m)));
      }
    }
    setTyping(false);
    if (!ctl.signal.aborted) setRunning(false);
  }

  function start() { setShown(0); void run(0); }
  const pauseRun = () => { stop.current?.abort(); stopSpeaking(); setTyping(false); setRunning(false); };
  const resume = () => void run(shown);
  const skip = () => { pauseRun(); setShown(msgs.length); };

  return (
    <section className="card p-5 grid gap-4" aria-label="The debate">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-lg font-semibold m-0">The debate</h3>
          <p className="mute text-sm m-0 mt-1 max-w-2xl">Opening statements, the face-offs between investors who disagree, and the final verdict. Every line is taken from the investors' own checks.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <label className="text-xs mute flex items-center gap-1.5" title={voice.data?.enabled ? "Each investor speaks in their own voice" : "Voices are off: add ELEVENLABS_API_KEY to the server's .env"}>
            <input type="checkbox" checked={useVoice} disabled={!voice.data?.enabled || running} onChange={(e) => setUseVoice(e.target.checked)} /> Voices
          </label>
          {!running && shown === 0 && <button className="btn" onClick={start}>Start the debate</button>}
          {running && <button className="btn ghost" onClick={pauseRun}>Pause</button>}
          {!running && shown > 0 && !done && <button className="btn" onClick={resume}>Resume</button>}
          {!done && shown > 0 && <button className="btn ghost" onClick={skip}>Skip to the verdict</button>}
          {done && <button className="btn ghost" onClick={start}>Replay</button>}
        </div>
      </div>

      <div role="log" aria-live="polite" className="grid gap-2.5 max-h-[560px] overflow-y-auto pr-1" style={{ minHeight: shown ? 120 : 0 }}>
        {msgs.slice(0, shown).map((m, i) => <Line key={i} m={m} lenses={a.lenses} a={a} />)}
        {typing && <div className="mute text-xs pl-11">…</div>}
        <div ref={bottom} />
      </div>
      {shown === 0 && <p className="m-0 mute text-sm">Press “Start the debate” to watch the panel argue it out.</p>}
    </section>
  );
}

function Line({ m, lenses, a }: { m: Msg; lenses: Lens[]; a: Analysis }) {
  if (m.kind === "heading") return <div className="text-xs font-semibold mute pt-2" style={{ borderTop: "1px solid var(--line)" }}>{m.text}</div>;
  if (m.kind === "moderator") return <p className="m-0 text-sm mute italic">{m.text}</p>;
  if (m.kind === "verdict") {
    const c = TONE[a.panel?.tone ?? a.overall.tone].color;
    return (
      <div className="rounded-xl p-4 grid gap-1.5" style={{ background: `color-mix(in srgb, ${c} 10%, transparent)`, border: `1px solid color-mix(in srgb, ${c} 40%, var(--line))` }}>
        <b style={{ color: c }} className="text-base">{m.text}</b>
        <span className="text-sm">{m.detail}</span>
        <span className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
          {lenses.map((l) => <span key={l.key}>{surname(l)}: <b style={{ color: l.decision ? CALL_COLOR[l.decision.call] : undefined }}>{l.decision?.label ?? l.word}</b></span>)}
        </span>
        <span className="mute text-[11px]">Each call is that investor's rules applied to the filings: a reading of the evidence, not personal advice.</span>
      </div>
    );
  }
  const l = lenses[m.who!], c = l.decision ? CALL_COLOR[l.decision.call] : "var(--mute)";
  const tag = m.role === "ruling" ? "Judge" : m.role === "objection" ? "Objects" : m.role === "case" ? "Makes the case" : "Opening";
  return (
    <div className="flex gap-3 items-start">
      <span aria-hidden className="inline-grid place-items-center w-8 h-8 rounded-full text-sm font-bold shrink-0" style={{ background: `color-mix(in srgb, ${c} 22%, transparent)`, color: c }}>{surname(l)[0]}</span>
      <div className="grid gap-0.5 min-w-0 rounded-xl px-3 py-2" style={{ background: m.role === "ruling" ? "color-mix(in srgb, #e6c350 12%, var(--panel2))" : "var(--panel2)" }}>
        <span className="text-xs"><b>{l.name}</b> <span className="mute">· {tag}</span></span>
        <span className="text-sm leading-relaxed">{m.text}</span>
        {m.detail && <span className="mute text-xs leading-snug">{m.role === "case" || m.role === "objection" ? `Idea: ${m.detail}` : m.detail}</span>}
      </div>
    </div>
  );
}
