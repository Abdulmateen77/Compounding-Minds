import { useEffect, useMemo, useRef, useState } from "react";
import { CALL_COLOR, TONE, type Analysis, type Lens } from "../research";
import { pickFaceOffs, surname } from "../scene/lenses";
import { Avatar } from "./Avatar";
import { Switch } from "./bits";
import { fact, opening } from "./firstPerson";
import { fetchVoice, playVoice, stopSpeaking, useVoiceStatus } from "../voice";
import { Say } from "./Say";
import { spokenForm, useEffectiveLevel } from "../literacy";

/* The debate as a chat log. Every line comes from the report: each investor's reading and call, the face-offs picked from their
   own checks (a case, an objection, the judge's ruling), and the panel's verdict. Nothing is invented for the debate. */

type Msg = { kind: "moderator" | "investor" | "heading" | "verdict"; who?: number; role?: "opening" | "case" | "objection" | "ruling"; text: string; detail?: string };

/** What is on screen right now, for the scene to show over the speaker's head (who null: the moderator or the verdict). */
export type Speech = { who: number | null; tag: string; text: string };

const TAG = { opening: "Opening statement", case: "My case", objection: "I object", ruling: "My ruling" } as const;

function script(a: Analysis, company: string): Msg[] {
  const L = a.lenses, out: Msg[] = [];
  out.push({ kind: "moderator", text: `The question for the panel: is ${company} worth investing in? ${L.length} investors, each judging by their own rules and the company's filings.` });
  out.push({ kind: "heading", text: "Opening statements" });
  L.forEach((l, i) => out.push({ kind: "investor", who: i, role: "opening", text: opening(l) }));
  const faceoffs = pickFaceOffs(L);
  if (!faceoffs.length) out.push({ kind: "moderator", text: "They read it much the same way, so there is no face-off." });
  faceoffs.forEach((f, k) => {
    out.push({ kind: "heading", text: `Face-off${faceoffs.length > 1 ? ` ${k + 1} of ${faceoffs.length}` : ""}: ${surname(L[f.pair[0]])} vs ${surname(L[f.pair[1]])}` });
    f.turns.forEach((t) => {
      const q = t.quote, said = `${fact(q.head, q.shown)}.`;
      if (t.role === "ruling") out.push({ kind: "investor", who: t.by, role: "ruling", text: `${t.headline ?? "I call it a split."} On my own checks: ${said}` });
      else if (t.role === "objection") out.push({ kind: "investor", who: t.by, role: "objection", text: `${surname(L[t.to])}, I see it differently. ${said}`, detail: q.idea });
      else out.push({ kind: "investor", who: t.by, role: "case", text: `Here is why I'm confident. ${said}`, detail: q.idea });
    });
  });
  out.push({ kind: "heading", text: "Final verdict" });
  out.push({ kind: "verdict", text: a.panel?.headline ?? a.overall.headline, detail: `${a.overall.headline}. ${a.overall.why}` });
  return out;
}

const speechOf = (m: Msg, a: Analysis): Speech | null =>
  m.kind === "heading" ? null
    : m.kind === "investor" ? { who: m.who!, tag: TAG[m.role!], text: m.text }
      : { who: null, tag: m.kind === "verdict" ? "The panel's verdict" : "Moderator", text: m.kind === "verdict" ? `${m.text}. ${a.overall.headline}.` : m.text };

const spoken = (m: Msg) => [m.text, m.detail && m.role !== "case" && m.role !== "objection" ? m.detail : ""].filter(Boolean).join(" ");
const pause = (m: Msg) => (m.kind === "heading" ? 700 : Math.min(4200, 1100 + (m.text.length + (m.detail?.length ?? 0)) * 18));

export function DebateLog({ a, company, onSpeak, heading = true }: { a: Analysis; company: string; onSpeak?: (s: Speech | null) => void; heading?: boolean }) {
  const msgs = useMemo(() => script(a, company), [a, company]);
  const voice = useVoiceStatus();
  const level = useEffectiveLevel();
  const levelRef = useRef(level);              // what the voices read out follows the reader's level (abbreviations said in full)
  levelRef.current = level;
  const [shown, setShown] = useState(0);              // how many lines are visible
  const [running, setRunning] = useState(false);
  const [useVoice, setUseVoice] = useState(false);
  const [speed, setSpeed] = useState(2);             // 1x to 2x: the voices and the pauses between lines (fast by default: a full debate is long)
  const speedRef = useRef(speed);
  speedRef.current = speed;
  const [typing, setTyping] = useState(false);
  const log = useRef<HTMLDivElement | null>(null);
  const stop = useRef<AbortController | null>(null);
  const done = shown >= msgs.length;

  // keep the newest line in view by scrolling the log itself, never the page
  useEffect(() => { const el = log.current; if (el && shown > 0) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" }); }, [shown, typing]);
  useEffect(() => () => { stop.current?.abort(); stopSpeaking(); onSpeak?.(null); }, []);   // eslint-disable-line react-hooks/exhaustive-deps
  // a link with "debate=play" starts the debate on arrival (for showing it to a room)
  useEffect(() => { if (/[?&]debate=play/.test(window.location.href)) start(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  async function run(from: number) {
    stop.current?.abort();
    const ctl = new AbortController();
    stop.current = ctl;
    setRunning(true);
    const withVoice = useVoice && !!voice.data?.enabled;
    // a line's audio is fetched before its text appears, so the voice starts the moment the text does; the next line is fetched while this one plays
    const audio = new Map<number, Promise<string | null>>();
    const load = (i: number) => {
      while (i < msgs.length && msgs[i].kind === "heading") i++;   // headings are silent: fetch the next spoken line during their pause
      if (!withVoice || i >= msgs.length || audio.has(i)) return;
      const m = msgs[i], who = m.kind === "investor" && m.who != null ? a.lenses[m.who].key : "judge";
      audio.set(i, fetchVoice(who, spokenForm(spoken(m), levelRef.current), ctl.signal).catch(() => null));
    };
    try {
      load(from);
      for (let i = from; i < msgs.length && !ctl.signal.aborted; i++) {
        const m = msgs[i];
        setTyping(m.kind === "investor");
        const [url] = await Promise.all([audio.get(i) ?? null, new Promise((r) => setTimeout(r, (m.kind === "investor" ? 650 : 250) / speedRef.current))]);
        audio.delete(i);
        if (ctl.signal.aborted) { if (url) URL.revokeObjectURL(url); break; }
        load(i + 1);
        setTyping(false);
        setShown(i + 1);
        const sp = speechOf(m, a);
        if (sp) onSpeak?.(sp);
        if (url) {
          try { await playVoice(url, ctl.signal, speedRef.current); } catch { await new Promise((r) => setTimeout(r, pause(m) / speedRef.current)); }
        } else {
          await new Promise((r) => setTimeout(r, pause(m) / speedRef.current));
        }
      }
    } finally {
      for (const p of audio.values()) void p.then((u) => u && URL.revokeObjectURL(u));
    }
    setTyping(false);
    if (!ctl.signal.aborted) setRunning(false);
  }

  function start() { setShown(0); onSpeak?.(null); void run(0); }
  const pauseRun = () => { stop.current?.abort(); stopSpeaking(); setTyping(false); setRunning(false); };
  const resume = () => void run(shown);
  const skip = () => { pauseRun(); setShown(msgs.length); onSpeak?.(speechOf(msgs[msgs.length - 1], a)); };

  return (
    <section className="card p-5 grid gap-4" aria-label="The debate">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        {heading
          ? <div>
              <h3 className="text-lg font-semibold m-0">The debate</h3>
              <p className="mute text-sm m-0 mt-1 max-w-2xl">Opening statements, the face-offs between investors who disagree, and the final verdict. Every line is taken from the investors' own checks.</p>
            </div>
          : <p className="mute text-sm m-0 max-w-2xl">Opening statements, the face-offs between investors who disagree, then the final verdict.</p>}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs mute" title={voice.data?.enabled ? "AI-generated voices, one per investor: not the real people" : "Voices are off: add ELEVENLABS_API_KEY to the server's .env"}>
            <Switch checked={useVoice} disabled={!voice.data?.enabled || running} onChange={setUseVoice}>AI voices</Switch>
          </span>
          <label className="text-xs mute flex items-center gap-2">Speed
            <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} aria-label="Debate speed">
              <option value={1}>1x</option><option value={1.25}>1.25x</option><option value={1.5}>1.5x</option><option value={2}>2x</option>
            </select>
          </label>
          {!running && shown === 0 && <button className="btn" onClick={start}>Start the debate</button>}
          {running && <button className="btn ghost" onClick={pauseRun}>Pause</button>}
          {!running && shown > 0 && !done && <button className="btn" onClick={resume}>Resume</button>}
          {!done && shown > 0 && <button className="btn ghost" onClick={skip}>Skip to the verdict</button>}
          {done && <button className="btn ghost" onClick={start}>Replay</button>}
        </div>
      </div>

      {/* nothing to show before the debate starts: an empty log would still add a gap to the card */}
      <div ref={log} role="log" aria-live="polite" className={shown || typing ? "grid gap-3 max-h-[420px] overflow-y-auto pr-1" : "sr-only"} style={{ minHeight: shown ? 120 : 0 }}>
        {msgs.slice(0, shown).map((m, i) => <div key={i} style={{ animation: "popin var(--duration-slow) var(--ease-soft) both" }}><Line m={m} lenses={a.lenses} a={a} /></div>)}
        {typing && <div className="mute text-xs pl-11">…</div>}
      </div>
      {shown === 0 && (
        // a preview of how it opens, so the card is not an empty box before it starts
        <div className="grid gap-3" aria-hidden style={{ opacity: 0.55, maxHeight: 190, overflow: "hidden", maskImage: "linear-gradient(#000 40%, transparent)", WebkitMaskImage: "linear-gradient(#000 40%, transparent)" }}>
          {msgs.slice(0, 4).map((m, i) => <Line key={i} m={m} lenses={a.lenses} a={a} />)}
        </div>
      )}
      {shown === 0 && <p className="m-0 mute text-sm">Press “Start the debate” to watch the panel argue it out; each line is also said in the office above.</p>}
    </section>
  );
}

function Line({ m, lenses, a }: { m: Msg; lenses: Lens[]; a: Analysis }) {
  if (m.kind === "heading") return <div className="text-xs font-semibold mute pt-2" style={{ borderTop: "1px solid var(--divider)" }}>{m.text}</div>;
  if (m.kind === "moderator") return <p className="m-0 text-sm mute italic"><Say>{m.text}</Say></p>;
  if (m.kind === "verdict") {
    const c = TONE[a.panel?.tone ?? a.overall.tone].color;
    return (
      <div className="rounded-xl p-4 grid gap-2" style={{ background: `color-mix(in srgb, ${c} 10%, transparent)`, border: `1px solid color-mix(in srgb, ${c} 40%, var(--divider))` }}>
        <b style={{ color: c }} className="text-base"><Say>{m.text}</Say></b>
        <span className="text-sm"><Say>{m.detail}</Say></span>
        <span className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
          {lenses.map((l) => <span key={l.key}>{surname(l)}: <b style={{ color: l.decision ? CALL_COLOR[l.decision.call] : undefined }}>{l.decision?.label ?? l.word}</b></span>)}
        </span>
        <span className="mute text-xs">Each call is that investor's rules applied to the filings: a reading of the evidence, not personal advice.</span>
      </div>
    );
  }
  const l = lenses[m.who!], c = l.decision ? CALL_COLOR[l.decision.call] : "var(--muted)";
  const tag = TAG[m.role!];
  return (
    <div className="flex gap-3 items-start">
      <Avatar l={l} size={34} ring={c} />
      <div className="grid gap-1 min-w-0 rounded-xl px-3 py-2" style={{ background: m.role === "ruling" ? "color-mix(in srgb, #e6c350 12%, var(--card-alt))" : "var(--card-alt)" }}>
        <span className="text-xs"><b>{l.name}</b> <span className="mute">· {tag}</span></span>
        <span className="text-sm leading-relaxed"><Say>{m.text}</Say></span>
        {m.detail && <span className="mute text-xs leading-snug">Why it matters: <Say>{m.detail}</Say></span>}
      </div>
    </div>
  );
}
