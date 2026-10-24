import { memo, useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame, useThree } from "@react-three/fiber";
import { Analyst, type Pose } from "./Analyst";
import { Box } from "./Box";
import type { Director } from "./director";
import { Label } from "./Label";
import { Desk, Lights, Partition, Room, Table, useGlow } from "./Set";
import { C, LABEL_HEX, STANCE_HEX, clamp01, easeInOut, easeOutBack, lerp, type Look } from "./theme";
import { agentState, checkDoneAt, checkPlan, thinkProgress } from "./timeline";

/** `desk` and `deskRole` override the desk nameplate (default: the investor name and "<ROLE> AGENT"). */
export type CheckResult = "pass" | "partial" | "fail" | "unknown";
/** `results` are the outcomes of this investor's checks, in order; the desk keeps a tally of them as they come in. */
export type SceneAgent = { key: string; investor: string; role: string; look: Look; weight: number; evidence: Set<string>; desk?: string; deskRole?: string; results?: CheckResult[] };
export type SceneCard = { name: string; value: string };
/** `heading` and `footer` override the stamp's "EVIDENCE ASSESSMENT" and "CONFIDENCE n%" lines. */
export type SceneVerdict = { text: string; label: keyof typeof LABEL_HEX; confidence?: number; heading?: string; footer?: string } | null;
/** All the scene needs from an analyst's call: the colour of their light strip. */
export type StanceView = { stance: keyof typeof STANCE_HEX };
export type Orbit = { az: number; pol: number };
export type Els = { chips: (HTMLElement | null)[]; wchips: (HTMLElement | null)[]; bubble: HTMLElement | null; focus: number };

const SPACING = 2.2;
/** The desks stand on an arc facing the table, like a panel at a hearing: the ends come forward and turn in. */
const ARC_R = 9;
export function deskPose(i: number, n: number) {
  const th = ((i - (n - 1) / 2) * SPACING) / ARC_R;
  return { x: ARC_R * Math.sin(th), z: ARC_R * (1 - Math.cos(th)), yaw: -th };
}
export const deskX = (i: number, n: number) => deskPose(i, n).x;
/** A point given in desk i's own frame (x to its right, z toward the table) as a point in the room. */
export function toWorld(i: number, n: number, lx: number, ly: number, lz: number): [number, number, number] {
  const p = deskPose(i, n), c = Math.cos(p.yaw), s = Math.sin(p.yaw);
  return [p.x + lx * c + lz * s, ly, p.z - lx * s + lz * c];
}
const HEAD_Y = 2.5;
const TABLE_Z = 6.3;

type Props = {
  dir: Director; agents: SceneAgent[]; cards: SceneCard[]; verdict: SceneVerdict;
  getView: (i: number) => StanceView | undefined;
  orbit: React.RefObject<Orbit>; els: React.RefObject<Els>;
  company: { name: string; sector: string; asOf: string };
  onHover: (i: number | null) => void; onSelect: (i: number) => void;
};

/** Camera: fixed vantage that frames all desks for the canvas aspect, plus limited pointer orbit and a gentle follow of the speaker. */
function Rig({ dir, agents, orbit }: Pick<Props, "dir" | "agents" | "orbit">) {
  const { camera, size } = useThree();
  const cur = useRef({ az: 0, pol: 0, fx: 0, sz: 0 });
  useFrame((_, dt) => {
    const n = agents.length;
    const aspect = size.width / Math.max(1, size.height);
    // The ends of the arc come toward the camera and so look larger: frame them with room to spare.
    let widest = 0;
    for (let i = 0; i < n; i++) widest = Math.max(widest, Math.abs(deskPose(i, n).x));
    const need = (widest + 1.5) * 1.35;
    const dBase = Math.max(10.2, need / (Math.tan((35 * Math.PI) / 360) * aspect));
    const t = dir.clock;
    const intro = 1 + 0.12 * (1 - easeInOut(clamp01(t / 2.4)));
    // A face-off between two named desks: push in and centre on the pair, then ease back out.
    const ad = dir.activeDebate(t);
    const debate = ad ? easeInOut(clamp01((t - ad.start) / 0.6)) * easeInOut(clamp01((ad.end - t) / 0.6)) : 0;
    // Talking to one investor: lean in a little and keep them clear of the chat panel on the right.
    const spot = dir.spot;
    cur.current.sz += ((spot != null ? 1 : 0) - cur.current.sz) * (1 - Math.exp(-dt * 4));
    const d = dBase * intro * (1 - 0.22 * debate) * (1 - 0.16 * cur.current.sz);
    const k = 1 - Math.exp(-dt * 6);
    cur.current.az += (orbit.current.az - cur.current.az) * k;
    cur.current.pol += (orbit.current.pol - cur.current.pol) * k;
    let fx = 0;
    for (let i = 0; i < n; i++) if (agentState(dir.tl, i, t) === "speaking" || thinkProgress(dir.tl, i, t) != null) fx = deskX(i, n) * 0.25;
    if (debate > 0 && ad) {
      const mid = (deskX(ad.pair[0], n) + deskX(ad.pair[1], n)) / 2, sp = dir.speakerAt(t);
      fx = lerp(fx, sp?.judge ? lerp(mid, deskX(sp.who, n), 0.65) : mid, debate);      // the ruling: swing toward the judge
    }
    if (spot != null) fx = lerp(fx, deskX(spot, n) + 1.3, cur.current.sz);
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
      v.set(...toWorld(i, n, 0, HEAD_Y, -0.75)).project(camera);
      const x = (v.x * 0.5 + 0.5) * size.width, y = (-v.y * 0.5 + 0.5) * size.height;
      const chip = e.chips[i];
      if (chip) chip.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px) translate(-50%,-100%)`;
      const wc = e.wchips[i];
      if (wc) {
        v.set(...toWorld(i, n, 0, 0.3, 1.0)).project(camera);
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

/** A small colored block per check, set on the desk as each one is finished: a visible record that the work was done. */
function Tally({ i, n, results, dir }: { i: number; n: number; results: CheckResult[]; dir: Director }) {
  const refs = useRef<(THREE.Mesh | null)[]>([]);
  const HEX: Record<CheckResult, string> = { pass: "#2fd37c", partial: "#f5b13d", fail: "#ff5a67", unknown: "#6b7490" };
  useFrame(() => {
    const t = dir.clock, plan = checkPlan(dir.tl, i, results.length);
    results.forEach((_, k) => {
      const m = refs.current[k]; if (!m) return;
      const u = !plan ? 0 : clamp01((t - checkDoneAt(plan, k)) / 0.3);
      m.visible = u > 0;
      m.scale.setScalar(Math.max(0.0001, easeOutBack(u)));
    });
  });
  if (!results.length) return null;
  const w = Math.min(0.2, 1.5 / results.length);
  return (
    <group>
      {results.map((r, k) => (
        <mesh key={k} ref={(m) => { refs.current[k] = m; }} visible={false} position={[(k - (results.length - 1) / 2) * w, 0.95, 0.36]} castShadow>
          <boxGeometry args={[w * 0.78, 0.07, 0.15]} />
          <meshStandardMaterial color={HEX[r]} emissive={HEX[r]} emissiveIntensity={0.35} />
        </mesh>
      ))}
    </group>
  );
}

/** The judge's gavel: it comes up when they rule and knocks twice as the verdict lands. */
function Gavel({ dir, i }: { dir: Director; i: number }) {
  const g = useRef<THREE.Group>(null), arm = useRef<THREE.Group>(null);
  useFrame(() => {
    const m = g.current, a = arm.current; if (!m || !a) return;
    const sp = dir.speakerAt(dir.clock);
    const on = !!sp && sp.judge && sp.who === i;
    m.visible = on; if (!on || !sp) return;
    const k = clamp01((sp.u - 0.08) / 0.3);                              // the knocks, early in the ruling
    a.rotation.x = -1.0 + 1.0 * Math.abs(Math.sin(k * Math.PI * 2)) * (k < 1 ? 1 : 0);
  });
  return (
    <group ref={g} position={[0.5, 0.94, 0.05]} visible={false}>
      <Box p={[0, 0.02, 0]} s={[0.34, 0.04, 0.2]} c="#5a3a22" />
      <group ref={arm} position={[0, 0.05, 0.05]}>
        <Box p={[0, 0.17, 0]} s={[0.05, 0.34, 0.05]} c="#9b6b3d" />
        <Box p={[0, 0.36, 0]} s={[0.24, 0.12, 0.12]} c="#6b4423" />
      </group>
    </group>
  );
}

function AgentRig({ i, a, n, dir, getView, onHover, onSelect }: { i: number; a: SceneAgent; n: number; dir: Director; getView: Props["getView"]; onHover: Props["onHover"]; onSelect: Props["onSelect"] }) {
  const pose = deskPose(i, n);
  const glow = useRef<THREE.MeshStandardMaterial>(null);
  const dots = useRef<THREE.Group>(null);
  const gl = useThree((s) => s.gl);
  // Turn the head toward another desk, in this desk's own frame.
  const faceTo = (j: number) => Math.max(-0.7, Math.min(0.7, Math.atan2(deskX(j, n) - pose.x, 3) - pose.yaw));

  const getPose = (): Pose => {
    const t = dir.clock, st = agentState(dir.tl, i, t);
    const since = t - dir.tl.speak[i];
    const speaking = st === "speaking";
    const hop = speaking && since < 0.5 ? Math.sin((since / 0.5) * Math.PI) * 0.22 : 0;
    let turn = Math.sin(t * 1.2 + i * 2.1) * 0.15;
    // Only the investor whose turn it is to research works; the others wait their turn at their desks.
    const working = st === "thinking" && (dir.tl.thinkLen[i] <= 0 || thinkProgress(dir.tl, i, t) != null);
    if (working) turn = Math.sin(t * 1.5 + i) * 0.25;
    if (dir.researching) turn = Math.sin(t * 1.1 + i * 1.7) * 0.32;          // reading, looking between papers and the screen
    // A face-off: both face each other; whoever is making their point leans in and gestures, the other listens.
    const ad = dir.activeDebate(t), sp = dir.speakerAt(t);
    let arguing = 0, gesture = 0;
    if (ad) {
      const j = ad.pair.indexOf(i), judging = dir.faceoffs[ad.k].judge === i;
      // whoever is speaking turns to the one they address; the other two sides (and the judge) turn to the speaker
      if (sp) { if (sp.who === i) turn = faceTo(sp.other); else if (j >= 0 || judging) turn = faceTo(sp.who); }
      else if (j >= 0) turn = faceTo(ad.pair[1 - j]);
      if (sp?.who === i) { arguing = 1; gesture = Math.abs(Math.sin(t * 5)) * 0.05; }
    } else if (!dir.faceoffs.length && dir.tl.cross && t >= dir.tl.cross[0] && t < dir.tl.cross[1]) {
      const k = Math.floor((t - dir.tl.cross[0]) / 0.65) % Math.max(1, n - 1) + 1;
      turn = faceTo((i + k) % n);
    }
    const talking = dir.spot === i;
    if (talking) turn = 0;                                           // face the viewer
    const sinceReply = (performance.now() - dir.replyAt) / 1000;
    const nod = talking && sinceReply >= 0 && sinceReply < 0.5 ? Math.sin((sinceReply / 0.5) * Math.PI) * 0.22 : 0;
    const busyTyping = working || dir.researching || (talking && dir.busy);
    return { t: t * 30 + i * 17, typing: busyTyping ? 1 : st === "idle" ? 0.4 : 0.15, headTurn: turn, jump: hop + nod + gesture, glow: speaking || talking || arguing ? 0.6 : 0 };
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
    g.visible = (st === "thinking" && (dir.tl.thinkLen[i] <= 0 || thinkProgress(dir.tl, i, dir.clock) != null)) || (dir.spot === i && dir.busy)
      || (dir.researching && Math.sin(clock.elapsedTime * 1.3 + i * 1.1) > 0.2);   // thought dots take turns
    g.children.forEach((c, k) => { c.position.y = Math.sin(clock.elapsedTime * 5 - k * 0.8) * 0.07; });
  });

  return (
    <group position={[pose.x, 0, pose.z]} rotation={[0, pose.yaw, 0]}>
      <Desk p={[0, 0, 0]} name={a.desk ?? a.investor.toUpperCase()} role={a.deskRole ?? `${a.role.toUpperCase()} AGENT`} glowRef={glow} />
      <Analyst look={a.look} p={[0, 0, -0.75]} getPose={getPose} />
      {a.results && <Tally i={i} n={n} results={a.results} dir={dir} />}
      {a.results && <Gavel dir={dir} i={i} />}
      <group ref={dots} position={[0, 2.45, -0.75]} visible={false}>
        {[-0.22, 0, 0.22].map((dx) => (
          <mesh key={dx} position={[dx, 0, 0]}><boxGeometry args={[0.2, 0.2, 0.2]} /><meshBasicMaterial color="#ffffff" /></mesh>
        ))}
      </group>
      <mesh position={[0, 1.2, -0.2]}
        onPointerOver={(e) => { e.stopPropagation(); onHover(i); gl.domElement.style.cursor = "pointer"; }}
        onPointerOut={() => { onHover(null); gl.domElement.style.cursor = "grab"; }}
        onClick={(e) => { e.stopPropagation(); onSelect(i); }}>
        <boxGeometry args={[2.0, 2.6, 1.5]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  );
}

/** Peer review: an arrow arcs from desk to desk. In a face-off it runs from whoever is speaking to whoever is listening, again and
    again through their turn; in the old cross-examination it steps through every pair. */
function CrossArrows({ dir, n }: { dir: Director; n: number }) {
  const group = useRef<THREE.Group>(null);
  const SEG = 10, STEP = 0.7;
  const everyPair = useMemo<(readonly [number, number])[]>(() => Array.from({ length: n }, (_, i) => [i, (i + 1) % n] as const).filter(([a, b]) => a !== b), [n]);
  useFrame(() => {
    const g = group.current; if (!g) return;
    const t = dir.clock;
    let a = -1, b = -1, f = 0;
    const sp = dir.speakerAt(t);
    if (sp) {
      const w = dir.tl.debates[sp.k].turns[sp.turn];
      a = sp.who; b = sp.other; f = ((t - w.start) / 1.4) % 1;           // a pulse every 1.4 seconds of the turn
    } else if (!dir.faceoffs.length && dir.tl.cross && t >= dir.tl.cross[0] && t < dir.tl.cross[1]) {
      const local = (t - dir.tl.cross[0]) / STEP;
      [a, b] = everyPair[Math.floor(local) % everyPair.length]; f = local - Math.floor(local);
    }
    g.visible = a >= 0; if (a < 0) return;
    const A = toWorld(a, n, 0, 2.75, 0.3), B = toWorld(b, n, 0, 2.75, 0.3);
    g.children.forEach((c, k) => {
      const u = k / (SEG - 1);
      c.position.set(lerp(A[0], B[0], u), 2.75 + Math.sin(u * Math.PI) * 0.45, lerp(A[2], B[2], u));
      const reach = clamp01(f * 1.6 - u * 0.6);   // the arrow draws itself from a to b
      c.scale.setScalar(Math.max(0.0001, reach * (k === SEG - 1 ? 2.2 : 1) * clamp01((1 - f) * 5)));
    });
  });
  return (
    <group ref={group} visible={false}>
      {Array.from({ length: SEG }, (_, k) => (
        <mesh key={k}><boxGeometry args={[0.2, 0.2, 0.2]} /><meshBasicMaterial color={C.amber} /></mesh>
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

/** While the report is built: filings are handed out from the table to each investor's desk, one after another. */
function ResearchFlow({ dir, n }: { dir: Director; n: number }) {
  const refs = useRef<(THREE.Mesh | null)[]>([]);
  const PER = 3;
  const items = useMemo(() => Array.from({ length: n * PER }, (_, k) => ({ desk: k % n, off: Math.floor(k / n) / PER + (k % n) * 0.11 })), [n]);
  useFrame(({ clock }) => {
    items.forEach((it, k) => {
      const m = refs.current[k]; if (!m) return;
      m.visible = dir.researching;
      if (!dir.researching) return;
      const u = (clock.elapsedTime / 3.2 + it.off) % 1;
      const e = easeInOut(u), to = toWorld(it.desk, n, -0.55, 0.99, 0.18);
      m.position.set(lerp(0, to[0], e), lerp(1.0, 0.99, e) + Math.sin(e * Math.PI) * 1.5, lerp(TABLE_Z, to[2], e));
      m.rotation.set(0, e * 5 + it.desk, (1 - e) * 0.5);
      m.scale.setScalar(Math.max(0.0001, Math.min(1, u * 6) * Math.min(1, (1 - u) * 6)));
    });
  });
  return (
    <group>
      {items.map((_, k) => (
        <mesh key={k} ref={(m) => { refs.current[k] = m; }} visible={false} castShadow>
          <boxGeometry args={[0.5, 0.02, 0.66]} />
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
      m.scale.x = wdt; m.position.x = -0.85 + wdt / 2;
    });
  });
  return (
    <group>
      {agents.map((a, i) => {
        const p = deskPose(i, n);
        return (
          <group key={a.key} position={[p.x, 0, p.z]} rotation={[0, p.yaw, 0]}>
            <mesh ref={(m) => { refs.current[i] = m; }} position={[0, 0.08, 0.95]} visible={false}>
              <boxGeometry args={[1, 0.14, 0.2]} />
              <meshStandardMaterial color="#7b5cff" emissive="#7b5cff" emissiveIntensity={0.5} />
            </mesh>
          </group>
        );
      })}
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
      <Box p={[0, 0.89, 0]} s={[1.9, 0.06, 0.9]} c={hex} e={hex} ei={0.35} />
      <Label width={1.6} p={[0, 1.3, 0.05]} r={[-0.12, 0, 0]} spec={{
        w: 760, h: 300, bg: C.paper, border: hex, borderW: 16, radius: 20, gap: 8,
        lines: [
          { text: verdict.heading ?? "EVIDENCE ASSESSMENT", size: 30, weight: 800, color: C.terracotta, spacing: 3 },
          { text: verdict.text.toUpperCase(), size: verdict.text.length > 14 ? 60 : 84, weight: 900, color: C.ink },
          { text: verdict.footer ?? `CONFIDENCE ${Math.round((verdict.confidence ?? 0) * 100)}%`, size: 40, weight: 800, color: hex },
        ],
      }} />
    </group>
  );
}

/** A band on the floor that follows the arc the desks stand on, so the curve reads even from the front. */
function ArcRug({ n }: { n: number }) {
  const half = (((n - 1) / 2) * SPACING) / ARC_R + 0.16;
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.004, ARC_R]} receiveShadow>
      <ringGeometry args={[ARC_R - 0.5, ARC_R + 1.5, 64, 1, Math.PI / 2 - half, half * 2]} />
      <meshStandardMaterial color="#6b4a33" roughness={0.95} />
    </mesh>
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
          { text: [company.sector.toUpperCase(), company.asOf ? `AS OF ${company.asOf}` : ""].filter(Boolean).join("  ·  "), size: 34, weight: 700, color: C.terracotta, spacing: 2 },
        ],
      }} />
      <ArcRug n={n} />
      {Array.from({ length: n - 1 }, (_, i) => {
        const a = deskPose(i, n), b = deskPose(i + 1, n);
        return <Partition key={i} x={(a.x + b.x) / 2} z={(a.z + b.z) / 2 - 0.3} ry={(a.yaw + b.yaw) / 2} />;
      })}
      {agents.map((a, i) => <AgentRig key={a.key} i={i} a={a} n={n} dir={dir} getView={getView} onHover={p.onHover} onSelect={p.onSelect} />)}
      <Table p={[0, 0, TABLE_Z]} />
      <Filings dir={dir} />
      <ResearchFlow dir={dir} n={n} />
      <MetricCards dir={dir} cards={cards} agents={agents} n={n} />
      <CrossArrows dir={dir} n={n} />
      <WeightBars dir={dir} agents={agents} n={n} />
      <Stamp dir={dir} verdict={verdict} />
    </>
  );
}

export default memo(SceneContentsImpl);
