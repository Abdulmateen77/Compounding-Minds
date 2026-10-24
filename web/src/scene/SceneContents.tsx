import { memo, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import type { AgentView } from "../api/client";
import { Analyst, type Pose } from "./Analyst";
import { Box } from "./Box";
import type { Director } from "./director";
import { Label } from "./Label";
import { Desk, Lights, Partition, Room, Table, useGlow } from "./Set";
import { C, LABEL_HEX, STANCE_HEX, clamp01, easeInOut, easeOutBack, lerp, type Look } from "./theme";
import { agentState } from "./timeline";

export type SceneAgent = { key: string; investor: string; role: string; look: Look; weight: number; evidence: Set<string> };
export type SceneCard = { name: string; value: string };
export type SceneVerdict = { text: string; label: keyof typeof LABEL_HEX; confidence: number } | null;
export type Orbit = { az: number; pol: number };
export type Els = { chips: (HTMLElement | null)[]; wchips: (HTMLElement | null)[]; bubble: HTMLElement | null; focus: number };

const SPACING = 2.2;
export const deskX = (i: number, n: number) => (i - (n - 1) / 2) * SPACING;
const HEAD_Y = 2.5;
const TABLE_Z = 3.4;

type Props = {
  dir: Director; agents: SceneAgent[]; cards: SceneCard[]; verdict: SceneVerdict;
  getView: (i: number) => AgentView | undefined;
  orbit: React.RefObject<Orbit>; els: React.RefObject<Els>;
  company: { name: string; sector: string; asOf: string };
  onHover: (i: number | null) => void; onSelect: (i: number) => void;
};

/** Camera: fixed vantage that frames all desks for the canvas aspect, plus limited pointer orbit and a gentle follow of the speaker. */
function Rig({ dir, agents, orbit }: Pick<Props, "dir" | "agents" | "orbit">) {
  const { camera, size } = useThree();
  const cur = useRef({ az: 0, pol: 0, fx: 0 });
  useFrame((_, dt) => {
    const n = agents.length;
    const aspect = size.width / Math.max(1, size.height);
    const need = ((n - 1) / 2) * SPACING + 2.2;
    const dBase = Math.max(10.2, need / (Math.tan((35 * Math.PI) / 360) * aspect));
    const t = dir.clock;
    const intro = 1 + 0.12 * (1 - easeInOut(clamp01(t / 2.4)));
    const d = dBase * intro;
    const k = 1 - Math.exp(-dt * 6);
    cur.current.az += (orbit.current.az - cur.current.az) * k;
    cur.current.pol += (orbit.current.pol - cur.current.pol) * k;
    let fx = 0;
    for (let i = 0; i < n; i++) if (agentState(dir.tl, i, t) === "speaking") fx = deskX(i, n) * 0.25;
    cur.current.fx += (fx - cur.current.fx) * (1 - Math.exp(-dt * 3));
    const ty = 2.0, tz = -0.2;
    const ph = Math.atan2(1.9, d) + cur.current.pol;
    const az = cur.current.az;
    camera.position.set(cur.current.fx + d * Math.sin(az) * Math.cos(ph), ty + d * Math.sin(ph), tz + d * Math.cos(az) * Math.cos(ph));
    camera.lookAt(cur.current.fx, ty, tz);
  });
  return null;
}

/** Writes projected screen positions of desk heads straight into the DOM overlay (no React renders). */
function Projector({ agents, els }: Pick<Props, "agents" | "els">) {
  const { camera, size } = useThree();
  const v = useMemo(() => new THREE.Vector3(), []);
  useFrame(() => {
    const n = agents.length;
    const e = els.current;
    for (let i = 0; i < n; i++) {
      v.set(deskX(i, n), HEAD_Y, -0.75).project(camera);
      const x = (v.x * 0.5 + 0.5) * size.width, y = (-v.y * 0.5 + 0.5) * size.height;
      const chip = e.chips[i];
      if (chip) chip.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px) translate(-50%,-100%)`;
      const wc = e.wchips[i];
      if (wc) {
        v.set(deskX(i, n), 0.3, 1.0).project(camera);
        wc.style.transform = `translate(${((v.x * 0.5 + 0.5) * size.width).toFixed(1)}px,${((-v.y * 0.5 + 0.5) * size.height).toFixed(1)}px) translate(-50%,-50%)`;
      }
      if (i === e.focus && e.bubble) {
        const b = e.bubble, w = b.offsetWidth, h = b.offsetHeight;
        const bx = Math.min(size.width - w / 2 - 6, Math.max(w / 2 + 6, x));
        const by = Math.max(h + 6, y - 30);
        b.style.transform = `translate(${bx.toFixed(1)}px,${by.toFixed(1)}px) translate(-50%,-100%)`;
        b.style.setProperty("--tail", `${(x - bx).toFixed(1)}px`);
      }
    }
  });
  return null;
}

function AgentRig({ i, a, n, dir, getView, onHover, onSelect }: { i: number; a: SceneAgent; n: number; dir: Director; getView: Props["getView"]; onHover: Props["onHover"]; onSelect: Props["onSelect"] }) {
  const x = deskX(i, n);
  const glow = useRef<THREE.MeshStandardMaterial>(null);
  const dots = useRef<THREE.Group>(null);
  const gl = useThree((s) => s.gl);

  const getPose = (): Pose => {
    const t = dir.clock, st = agentState(dir.tl, i, t);
    const since = t - dir.tl.speak[i];
    const speaking = st === "speaking";
    const hop = speaking && since < 0.5 ? Math.sin((since / 0.5) * Math.PI) * 0.22 : 0;
    let turn = Math.sin(t * 1.2 + i * 2.1) * 0.15;
    if (st === "thinking") turn = Math.sin(t * 1.5 + i) * 0.25;
    if (dir.tl.cross && t >= dir.tl.cross[0] && t < dir.tl.cross[1]) {
      const k = Math.floor((t - dir.tl.cross[0]) / 0.65) % Math.max(1, n - 1) + 1;
      const target = (i + k) % n;
      turn = Math.max(-0.7, Math.min(0.7, Math.atan2(deskX(target, n) - x, 3)));
    }
    return { t: t * 30 + i * 17, typing: st === "thinking" ? 1 : st === "idle" ? 0.4 : 0.15, headTurn: turn, jump: hop, glow: speaking ? 0.6 : 0 };
  };

  useGlow(glow, (set) => {
    const t = dir.clock, st = agentState(dir.tl, i, t);
    const stance = getView(i)?.stance;
    if ((st === "speaking" || st === "done") && stance) {
      const k = st === "speaking" ? 0.9 + 0.2 * Math.sin(t * 5) : 0.55;
      set(STANCE_HEX[stance], k);
    } else set("#2a3150", 0);
  });

  useFrame(({ clock }) => {
    const g = dots.current; if (!g) return;
    const st = agentState(dir.tl, i, dir.clock);
    // Real time, so the dots keep bobbing while the stream is the thing we are waiting on.
    g.visible = st === "thinking";
    g.children.forEach((c, k) => { c.position.y = Math.sin(clock.elapsedTime * 5 - k * 0.8) * 0.07; });
  });

  return (
    <group>
      <Desk p={[x, 0, 0]} name={a.investor.toUpperCase()} role={`${a.role.toUpperCase()} AGENT`} glowRef={glow} />
      <Analyst look={a.look} p={[x, 0, -0.75]} getPose={getPose} />
      <group ref={dots} position={[x, 2.45, -0.75]} visible={false}>
        {[-0.22, 0, 0.22].map((dx) => (
          <mesh key={dx} position={[dx, 0, 0]}><boxGeometry args={[0.2, 0.2, 0.2]} /><meshBasicMaterial color="#ffffff" /></mesh>
        ))}
      </group>
      <mesh position={[x, 1.2, -0.2]}
        onPointerOver={(e) => { e.stopPropagation(); onHover(i); gl.domElement.style.cursor = "pointer"; }}
        onPointerOut={() => { onHover(null); gl.domElement.style.cursor = "grab"; }}
        onClick={(e) => { e.stopPropagation(); onSelect(i); }}>
        <boxGeometry args={[2.0, 2.6, 1.5]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  );
}

/** Peer review: one arrow at a time arcs from desk to desk, so the audience can follow who is looking at whom. */
function CrossArrows({ dir, n }: { dir: Director; n: number }) {
  const group = useRef<THREE.Group>(null);
  const SEG = 10, STEP = 0.7;
  const pairs = useMemo(() => Array.from({ length: n }, (_, i) => [i, (i + 1) % n] as const).filter(([a, b]) => a !== b), [n]);
  useFrame(() => {
    const g = group.current; if (!g) return;
    const cx = dir.tl.cross; const t = dir.clock;
    const on = !!cx && t >= cx[0] && t < cx[1];
    g.visible = on; if (!on) return;
    const local = (t - cx![0]) / STEP;
    const [a, b] = pairs[Math.floor(local) % pairs.length];
    const f = local - Math.floor(local);
    const ax = deskX(a, n), bx = deskX(b, n);
    g.children.forEach((c, s) => {
      const u = s / (SEG - 1);
      c.position.set(lerp(ax, bx, u), 2.75 + Math.sin(u * Math.PI) * 0.45, 0.3);
      const reach = clamp01(f * 1.6 - u * 0.6);   // the arrow draws itself from a to b
      c.scale.setScalar(Math.max(0.0001, reach * (s === SEG - 1 ? 2.2 : 1) * clamp01((1 - f) * 5)));
    });
  });
  return (
    <group ref={group} visible={false}>
      {Array.from({ length: SEG }, (_, s) => (
        <mesh key={s}><boxGeometry args={[0.2, 0.2, 0.2]} /><meshBasicMaterial color={C.amber} /></mesh>
      ))}
    </group>
  );
}

function Filings({ dir }: { dir: Director }) {
  const refs = useRef<(THREE.Mesh | null)[]>([]);
  const N = 8;
  const seeds = useMemo(() => Array.from({ length: N }, (_, k) => ({ sx: (k - 3.5) * 1.5, rot: (k % 3 - 1) * 0.25 + k * 0.4 })), []);
  useFrame(() => {
    const t = dir.clock;
    seeds.forEach((s, k) => {
      const m = refs.current[k]; if (!m) return;
      const u = clamp01((t - (0.1 + k * 0.25)) / 1.1);
      m.visible = u > 0;
      const e = easeInOut(u);
      m.position.set(lerp(s.sx, (k % 3 - 1) * 0.18, e), lerp(5.2, 0.9 + k * 0.026, e) + Math.sin(e * Math.PI) * 1.2, lerp(-2.6, TABLE_Z + (k % 2) * 0.06, e));
      m.rotation.set(0, lerp(s.rot * 3, s.rot * 0.4, e), (1 - e) * 0.6);
    });
  });
  return (
    <group>
      {seeds.map((_, k) => (
        <mesh key={k} ref={(m) => { refs.current[k] = m; }} visible={false} castShadow>
          <boxGeometry args={[0.62, 0.02, 0.84]} />
          <meshStandardMaterial color={k % 2 ? "#ffffff" : "#efe6d2"} roughness={0.9} />
        </mesh>
      ))}
    </group>
  );
}

function MetricCards({ dir, cards, agents, n }: { dir: Director; cards: SceneCard[]; agents: SceneAgent[]; n: number }) {
  const groups = useRef<(THREE.Group | null)[]>([]);
  const backs = useRef<(THREE.MeshStandardMaterial | null)[]>([]);
  const cols = Math.max(cards.length, 1);
  const w = Math.min(1.55, (n * SPACING) / cols - 0.1);
  const slot = (k: number): [number, number] => [(k - (cols - 1) / 2) * (w + 0.12), 3.55];
  useFrame(() => {
    const t = dir.clock;
    let hot = new Set<string>();
    for (let i = 0; i < agents.length; i++) if (agentState(dir.tl, i, t) === "speaking") hot = agents[i].evidence;
    cards.forEach((c, k) => {
      const g = groups.current[k]; if (!g) return;
      const u = clamp01((t - (dir.tl.metrics[0] + 0.1 + k * 0.28)) / 0.7);
      g.visible = u > 0;
      const [sx, sy] = slot(k);
      const e = easeInOut(u);
      g.position.set(lerp(0, sx, e), lerp(1.4, sy, e) + Math.sin(e * Math.PI) * 0.8, lerp(TABLE_Z - 0.1, -2.78, e));
      g.scale.setScalar(Math.max(0.0001, easeOutBack(u)));
      const m = backs.current[k];
      if (m) { const on = hot.has(c.name); m.emissive.set(on ? C.violet : "#000000"); m.emissiveIntensity = on ? 1 : 0; m.color.set(on ? "#4a3d9c" : "#2c345e"); }
    });
  });
  return (
    <group>
      {cards.map((c, k) => (
        <group key={c.name} ref={(g) => { groups.current[k] = g; }} visible={false}>
          <mesh position={[0, 0, -0.03]}>
            <boxGeometry args={[w + 0.06, (w * 200) / 420 + 0.06, 0.04]} />
            <meshStandardMaterial ref={(m) => { backs.current[k] = m; }} color="#2c345e" />
          </mesh>
          <Label width={w} spec={{
            w: 420, h: 200, bg: C.paper, radius: 14, gap: 6,
            lines: [
              { text: c.name.replace(/_/g, " ").toUpperCase(), size: c.name.length > 22 ? 26 : 30, weight: 800, color: C.terracotta },
              { text: c.value, size: 76, weight: 900, color: C.ink },
            ],
          }} />
        </group>
      ))}
    </group>
  );
}

function WeightBars({ dir, agents, n }: { dir: Director; agents: SceneAgent[]; n: number }) {
  const refs = useRef<(THREE.Mesh | null)[]>([]);
  const max = Math.max(...agents.map((a) => a.weight), 0.0001);
  useFrame(() => {
    const t = dir.clock;
    const u = clamp01((t - dir.tl.synth[0]) / 1.4);
    agents.forEach((a, i) => {
      const m = refs.current[i]; if (!m) return;
      m.visible = u > 0;
      const wdt = Math.max(0.0001, 1.7 * (a.weight / max) * easeInOut(u));
      m.scale.x = wdt; m.position.x = deskX(i, n) - 0.85 + wdt / 2;
    });
  });
  return (
    <group>
      {agents.map((a, i) => (
        <mesh key={a.key} ref={(m) => { refs.current[i] = m; }} position={[deskX(i, n), 0.08, 0.95]} visible={false}>
          <boxGeometry args={[1, 0.14, 0.2]} />
          <meshStandardMaterial color="#7b5cff" emissive="#7b5cff" emissiveIntensity={0.5} />
        </mesh>
      ))}
    </group>
  );
}

function Stamp({ dir, verdict }: { dir: Director; verdict: SceneVerdict }) {
  const g = useRef<THREE.Group>(null);
  useFrame(() => {
    const m = g.current; if (!m) return;
    const s = dir.clock - dir.tl.stamp;
    const k = s < 0 ? 0 : lerp(2.4, 1, clamp01(s / 0.22));
    m.scale.setScalar(Math.max(0.0001, k)); m.visible = k > 0.001;
    m.position.x = s > 0 && s < 0.4 ? Math.sin(s * 40) * 0.04 * (1 - s / 0.4) : 0;
  });
  if (!verdict) return null;
  const hex = LABEL_HEX[verdict.label];
  return (
    <group ref={g} position={[0, 0, TABLE_Z]} visible={false}>
      <Box p={[0, 0.89, 0]} s={[2.4, 0.06, 1.1]} c={hex} e={hex} ei={0.35} />
      <Label width={2.2} p={[0, 1.5, 0.05]} r={[-0.12, 0, 0]} spec={{
        w: 760, h: 300, bg: C.paper, border: hex, borderW: 16, radius: 20, gap: 8,
        lines: [
          { text: "EVIDENCE ASSESSMENT", size: 30, weight: 800, color: C.terracotta, spacing: 3 },
          { text: verdict.text.toUpperCase(), size: verdict.text.length > 14 ? 60 : 84, weight: 900, color: C.ink },
          { text: `CONFIDENCE ${Math.round(verdict.confidence * 100)}%`, size: 40, weight: 800, color: hex },
        ],
      }} />
    </group>
  );
}

function SceneContentsImpl(p: Props) {
  const { dir, agents, cards, verdict, getView, company } = p;
  const n = agents.length;
  const gl = useThree((s) => s.gl);
  useEffect(() => { gl.domElement.style.cursor = "grab"; }, [gl]);
  return (
    <>
      <Lights />
      <Rig dir={dir} agents={agents} orbit={p.orbit} />
      <Projector agents={agents} els={p.els} />
      <Room />
      <Label width={4.6} p={[0, 4.95, -2.85]} spec={{
        w: 920, h: 220, bg: C.paper, radius: 18, gap: 6,
        lines: [
          { text: company.name.toUpperCase(), size: company.name.length > 16 ? 76 : 100, weight: 900, color: C.ink },
          { text: `${company.sector.toUpperCase()}  ·  AS OF ${company.asOf}`, size: 34, weight: 700, color: C.terracotta, spacing: 2 },
        ],
      }} />
      {Array.from({ length: n - 1 }, (_, i) => <Partition key={i} x={(deskX(i, n) + deskX(i + 1, n)) / 2} />)}
      {agents.map((a, i) => <AgentRig key={a.key} i={i} a={a} n={n} dir={dir} getView={getView} onHover={p.onHover} onSelect={p.onSelect} />)}
      <Table p={[0, 0, TABLE_Z]} />
      <Filings dir={dir} />
      <MetricCards dir={dir} cards={cards} agents={agents} n={n} />
      <CrossArrows dir={dir} n={n} />
      <WeightBars dir={dir} agents={agents} n={n} />
      <Stamp dir={dir} verdict={verdict} />
    </>
  );
}

export default memo(SceneContentsImpl);
