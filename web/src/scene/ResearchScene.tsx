import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";
import { STANCE_COLOR } from "../api/client";
import type { ChatMsg } from "../chat";
import type { Lens, Overall } from "../research";
import { Director, useDirectorTick } from "./director";
import { InvestorRoster } from "../components/InvestorRoster";
import InvestorPanel from "./InvestorPanel";
import { ThinkingCards } from "./ThinkingCards";
import type { Speech } from "../components/DebateLog";
import { Avatar } from "../components/Avatar";
import SceneContents, { type Els, type Orbit, type SceneAgent, type SceneCard, type SceneVerdict, type StanceView } from "./SceneContents";
import {
  MARK, checkLabel, counts, cut, pickFaceOffs, readingOf, speakSeconds, stanceOf, surname, thinkSeconds, faceTurnSeconds, typed,
  type FaceTurn,
} from "./lenses";
import { SPEEDS, getPrefs, setPrefs } from "../prefs";
import { loadProgress, saveProgress } from "./progress";
import { lookFor } from "./theme";
import { agentState, checkPlan, checkState, phaseAt, thinkProgress, type Phase } from "./timeline";

/* The investor panel of the research report, staged in the voxel office on a curved panel. Each investor works through their own
   checks (what they ask, what they find, the idea behind it), then gives their reading in their own words; investors who really
   disagree argue it out, turn by turn; then the overall reading is stamped. There can be no face-off, one, or several.

   Everything shown is already in the report (research/analysis.py computed it; the written view is the model's summary of those
   checks). The only thing decided here is the pacing, and it comes from the content: a research window is one slot per check, a
   reading is as long as its text, and a turn in a face-off is as long as what is said in it. */

type Props = {
  cik: number;           // for the one-on-one chat
  name: string;          // company name
  sub: string;           // e.g. "AAPL · Nasdaq", shown under the name on the wall
  asOf: string;
  lenses: Lens[];
  cards: SceneCard[];    // the figures that fly in from the table
  overall: Overall;
  onFail: (why: string) => void;
  demo?: boolean;        // presenter mode: big type, no toolbar, keyboard stepping, loops
  onExitDemo?: () => void;
  fromLoading?: boolean; // the investors were just shown researching: carry on from the end of the opening, not from the start
  debates?: boolean;
  speech?: Speech | null; // the debate's current line (Investor panel tab), said over the speaker's head
  thinkingBelow?: boolean; // the Investor panel tab: what each investor is thinking goes in cards under the scene, not over their head
};

const ORBIT_AZ = 0.5, ORBIT_POL = 0.2;
const DEMO_SPEED = 1.5, DEMO_LOOP_AFTER_MS = 9000;

const lastName = (full: string) => full.trim().split(/\s+/).slice(-1)[0].toUpperCase();
const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

const SHORT: Record<string, string> = { look: "Worth a look", wait: "Wait for price", avoid: "Avoid for now", weak: "Be careful", mixed: "Mixed evidence" };
const LABEL_FOR = { good: "investable", watch: "watch", warn: "not_investable" } as const;

const CAPTION: Record<Phase, [string, string]> = {
  ingest: ["Reading the SEC filings", "Annual and quarterly reports, as the company filed them"],
  metrics: ["Computing the numbers", "Python does all the arithmetic; each figure names its filing"],
  committee: ["The investors weigh in", "Each one runs their own habits of mind over the same numbers"],
  cross_exam: ["Where they disagree", ""],
  synthesis: ["Putting it together", "How well each investor's checks fit, then the overall reading"],
  done: ["Reading ready", "Scroll down for every check and its source"],
};

const toggleFullscreen = () => {
  try {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void document.documentElement.requestFullscreen?.();
  } catch { /* fullscreen is a convenience; the scene works without it */ }
};

const Caret = () => <span aria-hidden className="inline-block w-[0.5ch] opacity-70" style={{ animation: "dots 1s infinite" }}>▍</span>;

/** A line of the debate, said by the investor over their own head: who, which turn it is, and the words typed out as they say them. */
function SpeechCard({ lens, speech, big, color }: { lens: Lens; speech: Speech; big: boolean; color: string }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    setN(0);
    const id = window.setInterval(() => setN((k) => (k >= speech.text.length ? (window.clearInterval(id), k) : k + 2)), 30);
    return () => window.clearInterval(id);
  }, [speech.text]);
  return (
    <div className={`rounded-xl p-3 shadow-xl grid gap-2 ${big ? "text-base" : "text-sm"}`} style={{ background: "var(--card)", border: `2px solid ${speech.tag === "My ruling" ? "#e6c350" : color}`, color: "var(--foreground)" }}>
      <div className="flex items-center gap-2">
        <Avatar l={lens} size={26} />
        <b className="leading-tight">{lens.name}</b>
        <span className="mute text-xs ml-auto">{speech.tag}</span>
      </div>
      <div style={{ lineHeight: 1.4 }}>“{speech.text.slice(0, n)}{n < speech.text.length ? <Caret /> : "”"}</div>
    </div>
  );
}

/** The investor's notebook while they work: what they have asked and found so far, and the question they are on, typed out. */
function Notebook({ lens, i, dir, big, color }: { lens: Lens; i: number; dir: Director; big: boolean; color: string }) {
  const m = lens.checks.length, t = dir.clock;
  const st = checkState(dir.tl, i, t, m), plan = checkPlan(dir.tl, i, m);
  if (!st || !plan) return null;
  const last = st.current ?? st.done - 1;
  const from = Math.max(0, last - 3);
  const rows = lens.checks.slice(from, last + 1).map((k, o) => ({ k, idx: from + o }));
  const text = big ? "text-sm" : "text-xs";
  return (
    <div className={`rounded-xl p-3 shadow-xl ${big ? "text-base" : "text-sm"}`} style={{ background: "var(--card)", border: `2px solid ${color}`, color: "var(--foreground)" }}>
      <div className="flex items-center justify-between gap-2">
        <b>{lens.name}</b>
        <span className="chip num">{Math.min(m, st.done + (st.current != null && st.current >= st.done ? 1 : 0))} of {m} checks</span>
      </div>
      <div className="h-1 rounded-full overflow-hidden my-2" style={{ background: "var(--divider)" }}>
        <div style={{ width: `${(Math.min(1, (st.done + (st.current != null ? st.phase : 0)) / m)) * 100}%`, height: "100%", background: color }} />
      </div>
      <ol className={`m-0 p-0 list-none grid gap-2 ${text}`} style={{ lineHeight: 1.35 }}>
        {rows.map(({ k, idx }) => {
          const working = idx === st.current && idx >= st.done;
          if (!working) {
            const M = MARK[k.result];
            return <li key={k.id} className="flex gap-2 items-start"><span style={{ color: M.color }} aria-hidden>{M.mark}</span><span><b className="font-medium">{checkLabel(k)}</b> <span className="num mute">{cut(k.shown, 70)}</span></span></li>;
          }
          const f = st.phase / 0.8;                                     // 0..1 through this check's working time
          const ask = k.check.slice(0, Math.floor(clamp01(f / 0.5) * k.check.length));
          const askDone = f >= 0.5;
          return (
            <li key={k.id} className="grid gap-1">
              <span><span className="mute">Asking:</span> {askDone ? k.check : ask}{!askDone && <Caret />}</span>
              {askDone && <span className="num"><span className="mute">Found:</span> {k.shown}{f < 0.85 && <Caret />}</span>}
              {f >= 0.85 && <span className="mute" style={{ fontSize: "0.92em" }}>Idea: {cut(k.principle, 120)}</span>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function ResearchScene({ cik, name, sub, asOf, lenses, cards, overall, onFail, demo = false, onExitDemo, fromLoading = false, debates = true, thinkingBelow = false, speech = null }: Props) {
  const n = lenses.length;
  // debates off (the Report tab): each investor analyses and gives a reading; the face-offs live on the Investor panel tab
  const faceoffs = useMemo(() => (debates ? pickFaceOffs(lenses) : []), [lenses, debates]);
  const readings = useMemo(() => lenses.map(readingOf), [lenses]);
  const dir = useMemo(() => {
    const d = new Director(n, false, {
      think: lenses.map(thinkSeconds),
      speak: readings.map(speakSeconds),
      debates: faceoffs.map((f) => f.turns.map(faceTurnSeconds)),
    });
    d.faceoffs = faceoffs.map((f) => ({ pair: f.pair, by: f.turns.map((turn) => turn.by), to: f.turns.map((turn) => turn.to), judge: f.judge?.by }));
    // Back where they left off: leaving the tab and returning must not start the prologue over.
    const restored = demo ? null : loadProgress(cik, d.tl.end.toFixed(1));
    if (restored) {
      d.clock = Math.min(restored.clock, d.tl.end);
      d.wasDone = restored.done;
      d.resumedAt = !restored.done && restored.clock > 2 && restored.clock < d.tl.end - 1 ? restored.clock : null;
    } else if (fromLoading) d.clock = d.tl.ingest[1];
    const saved = getPrefs().speed;                            // chosen when searching, or on the last visit
    d.speed = demo && saved === 1 ? DEMO_SPEED : saved;
    return d;
  }, [n, lenses, readings, faceoffs, demo, fromLoading, cik]);
  useEffect(() => { dir.start(); return () => dir.stop(); }, [dir]);
  // The data is all here already, so the clock never has to wait on a stream.
  dir.inputs = { calls: n, verdict: true, done: true, failed: false };
  useDirectorTick(dir);

  // The prologue is meant to be watched through: questions open once it has played to the end (or in presenter mode).
  const [seen, setSeen] = useState(false);
  const unlocked = demo || seen || dir.wasDone;
  const unlockedRef = useRef(unlocked); unlockedRef.current = unlocked;
  useEffect(() => { if (dir.finished) setSeen(true); });
  useEffect(() => {
    if (demo) return;
    const sig = dir.tl.end.toFixed(1);
    const save = () => saveProgress(cik, sig, { clock: dir.clock, done: unlockedRef.current || dir.finished });
    const id = window.setInterval(save, 1000);
    window.addEventListener("pagehide", save);
    document.addEventListener("visibilitychange", save);
    return () => { window.clearInterval(id); window.removeEventListener("pagehide", save); document.removeEventListener("visibilitychange", save); save(); };
  }, [dir, cik, demo]);
  const [resumed, setResumed] = useState(dir.resumedAt != null);
  useEffect(() => { if (!resumed) return; const id = window.setTimeout(() => setResumed(false), 9000); return () => window.clearTimeout(id); }, [resumed]);

  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  const agents = useMemo<SceneAgent[]>(() => lenses.map((l) => ({
    key: l.key, investor: l.name, role: l.key, look: lookFor(l.key, l.key), weight: l.fit ?? 0, evidence: new Set<string>(),
    desk: lastName(l.name), deskRole: "INVESTOR LENS", results: l.checks.map((k) => k.result),
  })), [lenses]);

  const views = useMemo<StanceView[]>(() => lenses.map((l) => ({ stance: stanceOf(l.fit) })), [lenses]);
  const getView = useCallback((i: number) => views[i], [views]);

  const sceneVerdict: SceneVerdict = useMemo(() => {
    const all = lenses.map(counts);
    const pass = all.reduce((s, c) => s + c.pass, 0), known = all.reduce((s, c) => s + c.known, 0);
    return { text: SHORT[overall.key] ?? "Overall reading", label: LABEL_FOR[overall.tone], heading: "OVERALL READING", footer: `${pass} OF ${known} CHECKS PASSED` };
  }, [lenses, overall]);

  const [hover, setHover] = useState<number | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [card, setCard] = useState<number | null>(null);      // the analysis pop-up (Investor panel tab)
  const [chats, setChats] = useState<Record<string, ChatMsg[]>>({});
  const [hint, setHint] = useState(true);
  const [large, setLarge] = useState(false);
  const wasPlaying = useRef(false);
  const opener = useRef<HTMLElement | null>(null);
  const orbit = useRef<Orbit>({ az: 0, pol: 0 });
  const els = useRef<Els>({ chips: [], wchips: [], bubble: null, focus: -1 });
  const drag = useRef<{ x: number; y: number; az: number; pol: number } | null>(null);

  const t = dir.clock, tl = dir.tl;
  const phase = phaseAt(tl, t);
  const idx = Array.from({ length: n }, (_, i) => i);
  const speaking = idx.find((i) => agentState(tl, i, t) === "speaking") ?? -1;
  const thinker = idx.find((i) => thinkProgress(tl, i, t) != null) ?? -1;
  const ad = dir.activeDebate(t), sp = dir.speakerAt(t);
  const said = speech?.who ?? null;
  const focus = said != null ? said : sel != null || (thinkingBelow && !demo) ? -1 : (hover ?? (ad ? -1 : speaking >= 0 ? speaking : thinker));
  els.current.focus = focus;
  dir.spot = sel;                                             // the camera and that investor lean toward the viewer

  // The beats you can jump to: each investor's research, each face-off, the overall reading.
  const starts = tl.speak.map((s, i) => s - tl.thinkLen[i]);
  const marks = [0, ...starts, ...tl.debates.map((d) => d.start), tl.synth[0], tl.stamp];

  // Presenter mode: autoplay is already on; the keyboard steps through the beats, and the scene loops by itself when it ends.
  useEffect(() => {
    if (!demo) return;
    const id = window.setTimeout(() => setHint(false), 12000);
    return () => window.clearTimeout(id);
  }, [demo]);
  useEffect(() => {
    if (!demo) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || /input|textarea|select/i.test((e.target as HTMLElement).tagName)) return;
      const k = e.key.toLowerCase();
      if (k === "arrowright" || k === "n" || k === "pagedown") dir.seek(marks.find((m) => m > dir.clock + 0.05) ?? dir.tl.end);
      else if (k === "arrowleft" || k === "p" || k === "pageup") dir.seek([...marks].reverse().find((m) => m < dir.clock - 0.8) ?? 0);
      else if (k === " ") dir.setPlaying(!dir.playing);
      else if (k === "r") dir.replay();
      else if (k === "s") dir.seek(dir.tl.end);
      else if (k === "f") toggleFullscreen();
      else if (k === "1" || k === "2" || k === "3") { const s = SPEEDS[Number(k) - 1]; dir.setSpeed(s); setPrefs({ speed: s }); }
      else if (k === "?" || k === "h") setHint((h) => !h);
      else if (k === "x") onExitDemo?.();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [demo, dir, onExitDemo]);   // eslint-disable-line react-hooks/exhaustive-deps
  const finished = dir.finished;
  useEffect(() => { if (speech && !dir.finished) dir.seek(dir.tl.end); }, [speech, dir]);
  useEffect(() => {
    if (!demo || !finished) return;
    const id = window.setTimeout(() => dir.replay(), DEMO_LOOP_AFTER_MS);
    return () => window.clearTimeout(id);
  }, [demo, finished, dir]);

  // Talking to an investor pauses the scene; closing the panel resumes it if it was running.
  const closePanel = () => {
    setSel(null); dir.busy = false;
    if (wasPlaying.current) dir.setPlaying(true);
    wasPlaying.current = false;
    opener.current?.focus({ preventScroll: true });          // keyboard users land back where they were
  };
  const choose = (i: number) => {
    if (!unlocked) return;                                   // questions open when the prologue has been watched through
    if (i === sel) { closePanel(); return; }
    if (sel == null) { wasPlaying.current = dir.playing; dir.setPlaying(false); opener.current = document.activeElement as HTMLElement | null; }
    setSel(i);
  };
  const jump = (to: number) => { dir.seek(to); dir.setPlaying(true); };
  const faceName = (k: number) => `${surname(lenses[faceoffs[k].pair[0]])} vs ${surname(lenses[faceoffs[k].pair[1]])}`;
  const who = thinker >= 0 ? thinker : speaking;
  const chapters = [
    { id: "filings", label: "Filings and numbers", at: 0, on: phase === "ingest" || phase === "metrics", sub: "" },
    { id: "investors", label: "The investors", at: starts[0], on: phase === "committee", sub: who >= 0 ? `Investor ${who + 1} of ${n}` : "" },
    ...(faceoffs.length ? [{ id: "faceoffs", label: faceoffs.length > 1 ? "The face-offs" : "The face-off", at: tl.debates[0].start, on: phase === "cross_exam", sub: ad ? (faceoffs.length > 1 ? `Face-off ${ad.k + 1} of ${faceoffs.length}` : faceName(0)) : "" }] : []),
    { id: "overall", label: "The overall reading", at: tl.synth[0], on: phase === "synthesis" || phase === "done", sub: "" },
  ];
  const now = Math.max(0, chapters.findIndex((c) => c.on));

  const orbitBy = (daz: number, dpol: number) => {
    orbit.current.az = Math.max(-ORBIT_AZ, Math.min(ORBIT_AZ, orbit.current.az + daz));
    orbit.current.pol = Math.max(-ORBIT_POL * 0.6, Math.min(ORBIT_POL, orbit.current.pol + dpol));
  };
  const onKey = (e: React.KeyboardEvent) => {
    const k = e.key;
    if (k === "ArrowLeft") orbitBy(-0.08, 0); else if (k === "ArrowRight") orbitBy(0.08, 0);
    else if (k === "ArrowUp") orbitBy(0, 0.05); else if (k === "ArrowDown") orbitBy(0, -0.05);
    else if (k === " " && e.target === e.currentTarget) dir.setPlaying(!dir.playing);
    else if (k === "Escape") closePanel();
    else if (k === "0") orbit.current = { az: 0, pol: 0 };
    else return;
    e.preventDefault();
  };

  // What the floating card above an investor's head shows: their notebook while they research, their reading (typed) while they
  // give it, or a summary when you hover over someone the scene has not reached yet.
  const lens = focus >= 0 ? lenses[focus] : undefined;
  const lensColor = lens ? STANCE_COLOR[stanceOf(lens.fit)] : "transparent";
  const mode: "notebook" | "reading" | "summary" | null = focus < 0 ? null : focus === thinker && speaking !== focus ? "notebook" : focus === speaking ? "reading" : "summary";
  const readingNow = mode === "reading" ? typed(readings[focus], t - tl.speak[focus], 65) : lens ? cut(readings[focus], 190) : "";
  const readingTyping = mode === "reading" && readingNow.length < readings[focus].length;

  const showSynth = phase === "synthesis" || phase === "done";
  let [capHead, capDetail] = CAPTION[phase];
  if (phase === "committee") {
    if (thinker >= 0) { const m = lenses[thinker].checks.length, st = checkState(tl, thinker, t, m); capDetail = `${lenses[thinker].name} is working through ${m} checks (${Math.min(m, (st?.done ?? 0) + (st?.current != null && st.current >= (st?.done ?? 0) ? 1 : 0))} of ${m})`; }
    else if (speaking >= 0) capDetail = `${lenses[speaking].name} gives their reading`;
  }
  if (speech && speech.who == null) { capHead = speech.tag; capDetail = speech.text; }
  else if (ad && !speech) {
    const [a, b] = ad.pair;
    capHead = faceoffs.length > 1 ? `Face-off ${ad.k + 1} of ${faceoffs.length}` : "Face-off";
    capDetail = sp?.judge ? `Judge ${lenses[sp.who].name}: ${faceoffs[ad.k].turns[sp.turn].headline}` : `${lenses[a].name} (${lenses[a].word}) and ${lenses[b].name} (${lenses[b].word})`;
  } else if (phase === "synthesis" && faceoffs.length === 0) {
    capDetail = "No face-off: they all read it much the same way, so there was nothing to argue over";
  }
  const srLine = speaking >= 0
    ? `${lenses[speaking].name}: ${lenses[speaking].word}. ${readings[speaking]}`
    : thinker >= 0 ? `${lenses[thinker].name} starts working through ${lenses[thinker].checks.length} checks.`
      : sp ? `${lenses[sp.who].name} makes their point.` : `${capHead}${capDetail ? `. ${capDetail}` : ""}`;
  const big = demo || large;                                  // larger type: presenter mode, or the reader asked for it
  const bigStyle = big ? { fontSize: ".95rem" } : undefined;
  const small = big ? ".8rem" : ".72rem";

  /** One face-off turn as a card above its speaker's head: the check, what was found, the idea behind it; typed while they speak. The
      judge's ruling leads with the verdict, then the one of their own checks it rests on. */
  const TurnCard = ({ turn, f, live }: { turn: FaceTurn; f: number; live: boolean }) => {
    const q = turn.quote, ruling = turn.role === "ruling";
    const part = (str: string, from: number, to: number) => str.slice(0, Math.floor(clamp01((f - from) / (to - from)) * str.length));
    const b = ruling ? { h: [0, 0.25], head: [0.25, 0.5], shown: [0.5, 0.8] } : { h: [0, 0], head: [0, 0.4], shown: [0.4, 0.8] };
    const headline = ruling ? (live ? part(turn.headline ?? "", b.h[0], b.h[1]) : (turn.headline ?? "")) : "";
    const head = live ? part(q.head, b.head[0], b.head[1]) : q.head, shown = live ? part(q.shown, b.shown[0], b.shown[1]) : q.shown;
    const border = ruling ? "#e6c350" : q.color;
    return (
      <div className="rounded-lg px-2 py-1 leading-snug text-left" style={{ background: "var(--card)", border: `2px solid ${border}`, color: "var(--foreground)", maxWidth: big ? 300 : 225, fontSize: small, filter: live ? undefined : "brightness(0.72)" }}>
        <span className="mute" style={{ fontSize: "0.9em" }}>{ruling ? "The ruling" : turn.role === "case" ? "My case" : "My objection"}</span>
        {ruling && <div><b style={{ color: "#e6c350", fontSize: "1.1em" }}>{headline}</b>{live && f < 0.25 && <Caret />}</div>}
        {ruling && (!live || f >= 0.25) && <div className="mute" style={{ fontSize: "0.92em" }}>My own check:</div>}
        {(!ruling || !live || f >= 0.25) && <div><b style={{ color: q.color }}>{q.mark} {head}</b>{live && f >= b.head[0] && f < b.head[1] && <Caret />}</div>}
        {shown && <div className="num mute">{shown}{live && f >= b.shown[0] && f < b.shown[1] && <Caret />}</div>}
        {(!live || f >= 0.8) && <div className="mute" style={{ fontSize: "0.92em" }}>Idea: {q.idea}</div>}
      </div>
    );
  };

  return (
    <div>
      <div
        className="relative overflow-hidden select-none outline-none focus-visible:ring-2"
        style={{
          background: "#121831", aspectRatio: "16 / 9", touchAction: "pan-y",
          ...(demo
            ? { width: "min(100vw, calc(100vh * 16 / 9))", margin: "0 auto" }
            : { borderRadius: 16, border: "1px solid var(--divider)", minHeight: 380, width: "100%" }),
        }}
        tabIndex={0} role="group" aria-label="The investors read the company. Drag or use arrow keys to tilt the camera, space to pause."
        onKeyDown={demo ? undefined : onKey}
        onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, az: orbit.current.az, pol: orbit.current.pol }; }}
        onPointerMove={(e) => {
          const d = drag.current; if (!d || e.buttons === 0) return;
          const w = e.currentTarget.clientWidth;
          orbit.current.az = Math.max(-ORBIT_AZ, Math.min(ORBIT_AZ, d.az - ((e.clientX - d.x) / w) * 1.6));
          orbit.current.pol = Math.max(-ORBIT_POL * 0.6, Math.min(ORBIT_POL, d.pol + ((e.clientY - d.y) / w) * 1.2));
        }}
        onPointerUp={() => { drag.current = null; }}
        onPointerLeave={() => { drag.current = null; }}
      >
        <Canvas
          shadows dpr={[1, 2]} camera={{ fov: 35, position: [0, 3.6, 11], near: 0.1, far: 60 }}
          gl={{ antialias: true, powerPreference: "high-performance" }}
          onCreated={({ gl }) => gl.domElement.addEventListener("webglcontextlost", () => { if (alive.current) onFail("webgl context lost"); })}
        >
          <SceneContents dir={dir} agents={agents} cards={cards} verdict={sceneVerdict} getView={getView}
            orbit={orbit} els={els} company={{ name, sector: sub, asOf }}
            onHover={setHover} onSelect={thinkingBelow ? (i: number) => setCard(i) : choose} />
        </Canvas>

        {/* per desk: the face-off turns, then the reading */}
        {lenses.map((l, i) => {
          const st = agentState(tl, i, t), c = STANCE_COLOR[stanceOf(l.fit)];
          // in a face-off: the latest thing this investor has said so far (typed while they are speaking, faded once finished)
          let turnCard: { turn: FaceTurn; f: number; live: boolean } | null = null;
          if (ad) {
            const w = tl.debates[ad.k], turns = faceoffs[ad.k].turns;
            for (let j = turns.length - 1; j >= 0; j--) {
              if (turns[j].by !== i || t < w.turns[j].start) continue;
              const live = t < w.turns[j].end;
              turnCard = { turn: turns[j], f: clamp01((t - w.turns[j].start) / Math.max(0.1, w.turns[j].end - w.turns[j].start - 0.2)), live };
              break;
            }
          }
          const judging = !!ad && faceoffs[ad.k].judge?.by === i;
          return (
            <div key={l.key} ref={(el) => { els.current.chips[i] = el; }} className="absolute left-0 top-0 pointer-events-none flex flex-col items-center gap-1" style={{ willChange: "transform" }} aria-hidden="true">
              {judging && <span className="chip font-semibold" style={{ background: "var(--card)", color: "#e6c350", borderColor: "#e6c350", ...bigStyle }}>⚖ JUDGE</span>}
              {turnCard && <TurnCard {...turnCard} />}
              {(st === "speaking" || st === "done") && (
                <span className="chip font-semibold flex-col !gap-0 text-center leading-tight" style={{ background: "var(--card)", color: c, borderColor: c, borderRadius: 12, ...bigStyle }}>
                  {l.word.toUpperCase()}
                  {showSynth && l.fit != null && <span className="num font-normal" style={{ fontSize: small }}>fit {Math.round(l.fit * 100)}%</span>}
                </span>
              )}
            </div>
          );
        })}

        {/* the floating card above an investor: notebook, reading, or summary */}
        <div ref={(el) => { els.current.bubble = el; }} aria-hidden="true" className="absolute left-0 top-0 pointer-events-none"
          style={{ width: big ? 400 : 320, opacity: lens && focus >= 0 ? 1 : 0, transition: "opacity .2s", willChange: "transform" }}>
          {lens && said != null && <SpeechCard lens={lens} speech={speech!} big={big} color={lensColor} />}
          {lens && said == null && focus >= 0 && mode === "notebook" && <Notebook lens={lens} i={focus} dir={dir} big={big} color={lensColor} />}
          {lens && said == null && focus >= 0 && mode !== "notebook" && (
            <div className={`rounded-xl p-3 shadow-xl ${big ? "text-base" : "text-sm"}`} style={{ background: "var(--card)", border: `2px solid ${lensColor}`, color: "var(--foreground)" }}>
              <div className="flex items-center justify-between gap-2">
                <b>{lens.name}</b>
                <span className="chip num">{counts(lens).pass} of {counts(lens).known} checks</span>
              </div>
              <div className="mute text-xs mt-1">{lens.question}</div>
              <div className="mt-2"><b style={{ color: lensColor, fontSize: "1.05rem" }}>{lens.word.toUpperCase()}</b></div>
              <div className={`mt-1 ${big ? "text-sm" : "text-xs"}`} style={{ lineHeight: 1.4 }}>{readingNow}{readingTyping && <Caret />}</div>
            </div>
          )}
          <div style={{ width: 0, height: 0, margin: "0 auto", borderLeft: "8px solid transparent", borderRight: "8px solid transparent", borderTop: `8px solid ${lensColor}`, transform: "translateX(var(--tail,0px))" }} />
        </div>

        {/* caption and overall reading */}
        <div className="absolute left-3 bottom-3 right-3 flex items-end justify-between gap-3 pointer-events-none">
          <div className={`rounded-lg px-3 py-2 ${big ? "text-base" : "text-sm"}`} style={{ background: "color-mix(in srgb, var(--card) 88%, transparent)", border: "1px solid var(--divider)", maxWidth: "62%" }}>
            <b>{capHead}</b>{capDetail && <span className="mute"> · {capDetail}</span>}
          </div>
          {t >= tl.stamp && (
            <div className={`rounded-lg px-3 py-2 text-right pointer-events-auto max-w-[38%] ${big ? "text-base" : "text-sm"}`} style={{ background: "var(--card)", border: `2px solid var(--${overall.tone === "good" ? "green" : overall.tone === "watch" ? "amber" : "red"})` }}>
              <div className="font-bold">{overall.headline}</div>
            </div>
          )}
        </div>

        {/* once it has played (or after Skip to the end): where they disagreed, each face-off replayable, or that nobody did */}
        {t >= tl.stamp && sel == null && !speech && (
          <div className="absolute left-3 top-3 max-w-[46%] max-h-[62%] overflow-auto rounded-xl p-3 grid gap-2 pointer-events-auto content-start" style={{ background: "var(--card)", border: "1px solid var(--divider)" }}
            onPointerDown={(e) => e.stopPropagation()}>
            <div className="mute text-xs font-semibold uppercase tracking-wide">{faceoffs.length ? (faceoffs.length > 1 ? `${faceoffs.length} face-offs` : "Where they disagreed") : "No face-off"}</div>
            {faceoffs.length === 0 && <div className={big ? "text-sm" : "text-xs"} style={{ lineHeight: 1.4 }}>They all read it much the same way, so there was nothing to argue over.</div>}
            {faceoffs.map((f, k) => (
              <div key={k} className={`grid gap-1 ${big ? "text-sm" : "text-xs"}`} style={{ lineHeight: 1.35 }}>
                <div className="flex items-center justify-between gap-2">
                  <b>{faceName(k)}</b>
                  {unlocked && <button className="btn ghost sm" onClick={() => jump(tl.debates[k].start)}>Watch</button>}
                </div>
                {f.turns.filter((turn) => turn.role !== "ruling").slice(0, 2).map((turn, j) => (
                  <div key={j}><b style={{ color: turn.quote.color }}>{turn.quote.mark}</b> {surname(lenses[turn.by])}: {turn.quote.head}<span className="num mute"> · {turn.quote.shown}</span></div>
                ))}
                {f.judge && <div><b style={{ color: "#e6c350" }}>⚖ {surname(lenses[f.judge.by])}</b>: {f.turns[f.turns.length - 1].headline}</div>}
              </div>
            ))}
          </div>
        )}

        {/* one-on-one chat with the selected investor (also their checks) */}
        {sel != null && (
          <InvestorPanel key={lenses[sel].key} cik={cik} lens={lenses[sel]} big={big} onClose={closePanel}
            onBusy={(b) => { dir.busy = b; }} onReply={() => { dir.replyAt = performance.now(); }}
            messages={chats[lenses[sel].key] ?? []}
            setMessages={(f) => setChats((c) => ({ ...c, [lenses[sel].key]: f(c[lenses[sel].key] ?? []) }))} />
        )}

        {demo && (
          <>
            <div className="absolute left-0 right-0 bottom-0 h-1 pointer-events-none" style={{ background: "color-mix(in srgb, var(--divider) 60%, transparent)" }}>
              <div style={{ width: `${(t / tl.end) * 100}%`, height: "100%", background: "var(--primary)" }} />
            </div>
            <span className="absolute left-1/2 bottom-2 -translate-x-1/2 text-xs pointer-events-none" style={{ color: "var(--muted)" }}>{chapters[now].label}{chapters[now].sub ? ` · ${chapters[now].sub}` : ""} · {dir.speed}x</span>
            {hint && (
              <div className="absolute left-1/2 top-3 -translate-x-1/2 pointer-events-none rounded-full px-4 py-2 text-xs" style={{ background: "color-mix(in srgb, var(--card) 92%, transparent)", border: "1px solid var(--divider)", color: "var(--muted)" }}>
                → next · ← back · space pause · R replay · S end · F fullscreen · 1 2 3 speed · X exit
              </div>
            )}
          </>
        )}
        <div className="sr-only" aria-live="polite">{srLine}</div>
      </div>

      {!demo && (
        <>
          <p className="mt-3 mb-0 text-sm" role="status">
            {unlocked
              ? <><b>Prologue complete.</b> <span className="mute">Question any investor below, revisit a chapter, or replay it.</span></>
              : <><b>Prologue.</b> <span className="mute">Watch it through, each investor's research, their readings and the face-offs. Questions open when it ends.</span></>}
          </p>
          <ol className="m-0 mt-2 p-0 list-none flex flex-wrap gap-2 text-xs" aria-label="Prologue chapters">
            {chapters.map((c, k) => {
              const past = unlocked && dir.finished ? true : k < now, cur = !dir.finished && k === now;
              const style = cur ? { color: "var(--foreground)", borderColor: "var(--primary)", background: "color-mix(in srgb, var(--primary) 14%, transparent)" } : past ? { color: "var(--success)" } : { opacity: 0.6 };
              const label = <>{past && !cur ? "✓ " : ""}{c.label}{cur && c.sub ? <span className="mute"> · {c.sub}</span> : null}</>;
              return (
                <li key={c.id}>
                  {unlocked
                    ? <button className="chip cursor-pointer" style={{ minHeight: 40, ...style }} aria-current={cur ? "step" : undefined} onClick={() => jump(c.at)}>{label}</button>
                    : <span className="chip" style={{ minHeight: 40, ...style }} aria-current={cur ? "step" : undefined}>{label}</span>}
                </li>
              );
            })}
          </ol>
          {resumed && (
            <p className="mt-2 mb-0 text-xs mute" role="status">
              Resuming where you left off. <button className="underline bg-transparent border-0 cursor-pointer p-0" style={{ color: "var(--primary)" }} onClick={() => { dir.replay(); setResumed(false); }}>Start from the beginning</button>
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2 mt-3" role="toolbar" aria-label="Prologue controls">
            <button className="btn ghost" onClick={() => (dir.finished ? dir.replay() : dir.setPlaying(!dir.playing))} aria-pressed={!dir.playing && !dir.finished}>
              {dir.finished ? "Replay the prologue" : dir.playing ? "Pause" : "Resume"}
            </button>
            <div role="group" aria-label="Pace" className="flex items-center gap-1">
              <span className="mute text-xs mr-1">Pace</span>
              {SPEEDS.map((s) => (
                <button key={s} className="btn ghost num" aria-pressed={dir.speed === s} onClick={() => { dir.setSpeed(s); setPrefs({ speed: s }); }}
                  style={dir.speed === s ? { color: "var(--foreground)", borderColor: "var(--primary)" } : undefined}>{s}x</button>
              ))}
            </div>
            <button className="btn ghost" aria-pressed={large} onClick={() => setLarge((l) => !l)}>Larger text</button>
            <button className="btn ghost" onClick={() => { orbit.current = { az: 0, pol: 0 }; }}>Reset view</button>
          </div>
          {thinkingBelow
            ? <ThinkingCards lenses={lenses} tl={tl} t={t} unlocked={unlocked && dir.finished} open={card} setOpen={setCard} onAsk={choose} />
            : <div className="mt-3"><InvestorRoster lenses={lenses} sel={sel} onChoose={choose} locked={!unlocked} /></div>}
          <p className="mute text-xs mt-2 mb-0">{thinkingBelow ? "Click an investor, in the scene or on their card, for their analysis and vote. " : unlocked ? "Click an investor in the scene, or choose one above, to question them one-on-one about their reading. " : ""}Drag to tilt the camera. Space pauses; arrow keys tilt the camera.</p>
        </>
      )}
    </div>
  );
}
