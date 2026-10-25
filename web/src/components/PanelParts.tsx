import { useMemo, useRef, useState } from "react";
import { CALL_COLOR, TONE, type Analysis, type Lens } from "../research";
import { pickFaceOffs, surname } from "../scene/lenses";
import { playDebate, stopSpeaking, useVoiceStatus, type Line } from "../voice";
import { CallChip } from "./InvestorCards";
import { Say } from "./Say";
import { spokenForm, useEffectiveLevel } from "../literacy";

/** The headline over the investors' take (Report tab) and over the debates (Investor panel tab): the panel's tally, the overall
    reading, and each investor's call as a chip. */
export function PanelVerdict({ a, name, title }: { a: Analysis; name: string; title: string }) {
  const p = a.panel, o = a.overall;
  const color = p ? TONE[p.tone].color : TONE[o.tone].color;
  return (
    <section className="card p-6 md:p-7 grid gap-4" style={{ background: `linear-gradient(135deg, color-mix(in srgb, ${color} 12%, var(--card)), var(--card))`, borderColor: `color-mix(in srgb, ${color} 45%, var(--divider))` }}>
      <div>
        <p className="mute text-sm m-0">{title} {name}</p>
        <h2 className="text-2xl md:text-3xl font-bold my-1" style={{ color }}><Say>{p?.headline ?? o.headline}</Say></h2>
        <p className="m-0 max-w-3xl leading-relaxed">{p && <b>{o.headline}. </b>}<Say>{o.why}</Say></p>
      </div>
      <div className="flex flex-wrap gap-2" aria-label="Each investor's call">
        {a.lenses.map((l) => (
          <span key={l.key} className="flex items-center gap-2 text-sm">
            <span className="font-medium">{surname(l)}</span><CallChip l={l} />
          </span>
        ))}
      </div>
      {p && (
        <div className="flex h-2 rounded-full overflow-hidden" aria-hidden style={{ background: "var(--divider)" }}>
          {(["invest", "wait", "avoid"] as const).map((k) => p.counts[k] > 0 && <div key={k} style={{ flex: p.counts[k], background: CALL_COLOR[k] }} />)}
        </div>
      )}
      <p className="m-0 text-xs mute">Each call is that investor's rules applied to the filings: a reading of the evidence, not personal advice.</p>
    </section>
  );
}

/** The face-offs read aloud, each speaker in their own voice (ElevenLabs). Off, with a note, until the server has a key. */
export function DebateVoices({ lenses }: { lenses: Lens[] }) {
  const status = useVoiceStatus();
  const level = useEffectiveLevel();
  const faceoffs = useMemo(() => pickFaceOffs(lenses), [lenses]);
  const lines: Line[] = useMemo(() => faceoffs.flatMap((f) => f.turns.map((t) => {
    const who = lenses[t.by], q = t.quote;
    const text = t.role === "ruling" ? `${t.headline} ${q.head}: ${q.shown}.` : t.role === "objection" ? `But ${q.head.toLowerCase()} ${q.shown}.` : `${q.head} ${q.shown}.`;
    return { investor: who.key, name: who.name, text: spokenForm(text, level) };
  })), [faceoffs, lenses, level]);
  const [playing, setPlaying] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const ctl = useRef<AbortController | null>(null);

  if (!lines.length) return null;
  const on = status.data?.enabled;
  const start = () => {
    setErr(null);
    ctl.current = new AbortController();
    playDebate(lines, setPlaying, ctl.current.signal).catch((e) => setErr(String(e.message ?? e)));
  };
  const stop = () => { ctl.current?.abort(); stopSpeaking(); setPlaying(null); };

  return (
    <section className="card p-4 grid gap-2" aria-label="Listen to the face-offs">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <span className="font-semibold text-sm">Listen to the face-offs</span>
          <p className="m-0 mute text-xs">Each investor speaks in their own AI-generated voice (not the real people). {lines.length} lines, read from their own checks.</p>
        </div>
        {playing == null
          ? <button className="btn" disabled={!on} onClick={start} title={on ? "Play the debate" : "Voices are off: add ELEVENLABS_API_KEY to .env"}>Play</button>
          : <button className="btn ghost" onClick={stop}>Stop</button>}
      </div>
      {!on && <p className="m-0 text-xs" style={{ color: "var(--warning)" }}>Voices are off. Add an ElevenLabs key to the server's .env (ELEVENLABS_API_KEY) to hear the debate.</p>}
      {playing != null && <p className="m-0 text-sm"><b>{lines[playing].name}:</b> {lines[playing].text}</p>}
      {err && <p className="m-0 text-xs" style={{ color: "var(--error)" }}>{err}</p>}
    </section>
  );
}
