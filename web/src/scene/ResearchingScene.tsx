import { useEffect, useMemo, useRef } from "react";
import { Canvas } from "@react-three/fiber";
import { RESEARCH_STEPS } from "../research";
import { Director, useDirectorTick } from "./director";
import { PANEL } from "./panel";
import SceneContents, { type Els, type Orbit, type SceneAgent } from "./SceneContents";
import { lookFor } from "./theme";

/* The investor room while the report is being built: the six investors read and type, filings are handed out from the table to
   each desk, and the four steps of the lookup tick over. The clock loops inside the settled part of the opening so the camera
   does not pump; when the report arrives the real scene takes over from the same moment (see ResearchScene `fromLoading`). */

const LOOP_FROM = 2.6, LOOP_TO = 4.9;

type Props = { name?: string; step: number; seconds: number; onFail: (why: string) => void; demo?: boolean };

const mmss = (sec: number) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

export default function ResearchingScene({ name, step, seconds, onFail, demo = false }: Props) {
  const dir = useMemo(() => {
    const d = new Director(PANEL.length, false);
    d.researching = true;
    d.clock = LOOP_FROM;
    return d;
  }, []);
  useEffect(() => { dir.start(); return () => dir.stop(); }, [dir]);
  dir.inputs = { calls: 0, verdict: false, done: false, failed: false };
  dir.speed = 1;
  useDirectorTick(dir);
  // Keep the clock inside the settled stretch of the opening, so filings keep arriving and the camera stays put.
  useEffect(() => {
    const id = window.setInterval(() => { if (dir.clock > LOOP_TO) dir.seek(LOOP_FROM); }, 150);
    return () => window.clearInterval(id);
  }, [dir]);

  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const agents = useMemo<SceneAgent[]>(() => PANEL.map((p) => ({
    key: p.key, investor: p.name, role: p.key, look: lookFor(p.key, p.key), weight: 0, evidence: new Set<string>(),
    desk: p.name.trim().split(/\s+/).slice(-1)[0].toUpperCase(), deskRole: "INVESTOR LENS",
  })), []);
  const orbit = useRef<Orbit>({ az: 0, pol: 0 });
  const els = useRef<Els>({ chips: [], wchips: [], bubble: null, focus: -1 });
  const none = useMemo(() => [], []);

  const stepNow = Math.min(step, RESEARCH_STEPS.length - 1);
  const pct = Math.min(95, Math.round((seconds / 30) * 100));

  return (
    <div
      className="relative overflow-hidden select-none"
      style={{
        background: "#121831", aspectRatio: "16 / 9",
        ...(demo ? { width: "min(100vw, calc(100vh * 16 / 9))", margin: "0 auto" } : { borderRadius: 16, border: "1px solid var(--line)", minHeight: 380 }),
      }}
      role="group" aria-label="The investors are researching the company">
      <Canvas shadows dpr={[1, 2]} camera={{ fov: 35, position: [0, 3.6, 11], near: 0.1, far: 60 }} gl={{ antialias: true, powerPreference: "high-performance" }}
        onCreated={({ gl }) => gl.domElement.addEventListener("webglcontextlost", () => { if (alive.current) onFail("webgl context lost"); })}>
        <SceneContents dir={dir} agents={agents} cards={none} verdict={null} getView={() => undefined} orbit={orbit} els={els}
          company={{ name: name ?? "Researching…", sector: "", asOf: "" }} onHover={() => {}} onSelect={() => {}} />
      </Canvas>

      <div className="absolute left-3 top-3 rounded-xl p-3 grid gap-2 max-w-[min(22rem,60%)]" role="status" aria-live="polite"
        style={{ background: "color-mix(in srgb, var(--panel) 92%, transparent)", border: "1px solid var(--line)" }}>
        <div className={`font-semibold ${demo ? "text-base" : "text-sm"}`}>Researching {name ?? "the company"}…</div>
        <ol className={`m-0 p-0 list-none grid gap-1.5 ${demo ? "text-sm" : "text-xs"}`}>
          {RESEARCH_STEPS.map((s, k) => (
            <li key={s} className="flex items-center gap-2" style={{ opacity: k <= stepNow ? 1 : 0.4 }} aria-current={k === stepNow ? "step" : undefined}>
              <span aria-hidden className="inline-grid place-items-center w-4 h-4 rounded-full text-[10px] shrink-0"
                style={{ background: k < stepNow ? "var(--green)" : "var(--panel2)", color: k < stepNow ? "#06210f" : "var(--mute)" }}>{k < stepNow ? "✓" : k === stepNow ? "…" : ""}</span>
              <span>{s}</span>
              <span className="sr-only">{k < stepNow ? "done" : k === stepNow ? "in progress" : "waiting"}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="absolute left-3 bottom-4 right-3 flex items-end justify-between gap-3 pointer-events-none">
        <div className={`rounded-lg px-3 py-2 ${demo ? "text-base" : "text-sm"}`} style={{ background: "color-mix(in srgb, var(--panel) 88%, transparent)", border: "1px solid var(--line)", maxWidth: "70%" }}>
          <b>{RESEARCH_STEPS[stepNow]}</b>
          <span className="mute"> · the first lookup takes 20 to 30 seconds. Later ones are instant.</span>
        </div>
        <span className="num text-xs rounded-lg px-2 py-1" style={{ background: "color-mix(in srgb, var(--panel) 88%, transparent)", color: "var(--mute)" }}>{mmss(seconds)} elapsed</span>
      </div>
      <div className="absolute left-0 right-0 bottom-0 h-1 pointer-events-none" style={{ background: "color-mix(in srgb, var(--line) 60%, transparent)" }} role="progressbar" aria-label="Estimated progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
        <div style={{ width: `${pct}%`, height: "100%", background: "var(--blue)", transition: "width 1s linear" }} />
      </div>
    </div>
  );
}
