import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { Group, Mesh, MeshStandardMaterial } from "three";
import { Box } from "./Box";
import { Spring, frameDt } from "./smooth";
import { BOT, type Look } from "./theme";

type V3 = [number, number, number];

/** What the character should be doing right now, recomputed each frame by the caller from the director clock. These are targets, not
    positions: the analyst eases toward them, and keeps its own continuous time for everything ambient (sway, typing, breathing), so
    nothing here may be a function of the clock that can jump, loop or pause. */
export type Pose = {
  seed: number;
  typing: number;          // 0..1, how hard they are typing
  look: number | null;     // head yaw to settle on, or null to drift about idly
  sway: number;            // size of the idle drift (radians)
  swayRate: number;        // speed of the idle drift (radians per second)
  lift: number;            // hop, nod or gesture, lifting the whole body (scene units)
  glow: number;
};

const REST = -1.15, TAP_RATE = 26;

const DARK = BOT.ink;

const Glasses = () => (
  <group position={[0, 0.03, 0.4]}>
    {[-0.17, 0.17].map((x) => (
      <group key={x} position={[x, 0, 0]}>
        <Box p={[0, 0.1, 0]} s={[0.26, 0.04, 0.02]} c={DARK} shadow={false} />
        <Box p={[0, -0.1, 0]} s={[0.26, 0.04, 0.02]} c={DARK} shadow={false} />
        <Box p={[-0.11, 0, 0]} s={[0.04, 0.2, 0.02]} c={DARK} shadow={false} />
        <Box p={[0.11, 0, 0]} s={[0.04, 0.2, 0.02]} c={DARK} shadow={false} />
      </group>
    ))}
    <Box p={[0, 0.06, 0]} s={[0.1, 0.03, 0.02]} c={DARK} shadow={false} />
  </group>
);

const Hair = ({ style = "flat", c }: { style?: Look["hairStyle"]; c: string }) => {
  if (style === "bald") {
    return (<>
      <Box p={[-0.4, 0.02, -0.05]} s={[0.06, 0.28, 0.55]} c={c} />
      <Box p={[0.4, 0.02, -0.05]} s={[0.06, 0.28, 0.55]} c={c} />
      <Box p={[0, 0.02, -0.4]} s={[0.82, 0.28, 0.06]} c={c} />
    </>);
  }
  return (<>
    <Box p={[0, 0.44, 0]} s={[0.84, 0.16, 0.84]} c={c} />
    {style === "side" && (<>
      <Box p={[-0.41, 0.15, -0.05]} s={[0.06, 0.45, 0.7]} c={c} />
      <Box p={[0.41, 0.15, -0.05]} s={[0.06, 0.45, 0.7]} c={c} />
      <Box p={[0, 0.15, -0.41]} s={[0.84, 0.5, 0.06]} c={c} />
    </>)}
    {style === "swoop" && <Box p={[-0.12, 0.33, 0.39]} s={[0.6, 0.12, 0.1]} c={c} />}
    {style === "flat" && <Box p={[0, 0.2, -0.41]} s={[0.84, 0.4, 0.06]} c={c} />}
  </>);
};

const Arm = ({ side, shirt, skin, y, gref }: { side: -1 | 1; shirt: string; skin: string; y: number; gref: React.Ref<Group> }) => (
  <group ref={gref} position={[side * 0.56, y, 0]} rotation={[REST, 0, 0]}>
    <Box p={[0, -0.3, 0]} s={[0.22, 0.62, 0.24]} c={shirt} />
    <Box p={[0, -0.68, 0]} s={[0.2, 0.16, 0.2]} c={skin} />
  </group>
);

/** A seated blocky analyst. Origin is the floor point under the character. Animated imperatively (no re-render per frame). */
export function Analyst({ look, getPose, p = [0, 0, 0] }: { look: Look; getPose: () => Pose; p?: V3 }) {
  const skin = look.skin ?? BOT.skin;
  const root = useRef<Group>(null), body = useRef<Group>(null), head = useRef<Group>(null);
  const armL = useRef<Group>(null), armR = useRef<Group>(null), face = useRef<Mesh>(null);

  const sp = useRef({
    yaw: new Spring(), pitch: new Spring(), roll: new Spring(), typing: new Spring(), lift: new Spring(), glow: new Spring(),
    sway: new Spring(), rate: new Spring(), drift: 0, tap: 0, breath: 0,
  });

  useFrame((_, rawDt) => {
    const dt = frameDt(rawDt), k = sp.current, pose = getPose();
    // Time that belongs to this character alone: it runs through pauses, scrubs and loops, and a change of rate only bends it.
    const rate = k.rate.to(pose.swayRate, 0.5, dt), amp = k.sway.to(pose.sway, 0.5, dt), typing = k.typing.to(pose.typing, 0.35, dt);
    k.drift += rate * dt; k.tap += TAP_RATE * dt * (0.6 + 0.4 * typing); k.breath += dt;

    const idle = Math.sin(k.drift + pose.seed * 2.1) * amp;
    const aim = pose.look == null ? idle : pose.look + Math.sin(k.drift * 0.7 + pose.seed) * 0.025;
    const yaw = k.yaw.to(aim, 0.28, dt);
    // Head: turns, tilts toward the keyboard as they type, and leans a touch into a turn so it reads as a body, not a dial.
    const pitch = k.pitch.to(0.06 + typing * 0.1 + Math.sin(k.breath * 0.7 + pose.seed) * 0.012, 0.35, dt);
    const roll = k.roll.to(-yaw * 0.16, 0.3, dt);
    const lift = k.lift.to(pose.lift, 0.07, dt);
    const glow = k.glow.to(pose.glow, 0.18, dt);

    // Two hands that never tap in lockstep: different phases, and each stroke is eased so the finger lands and lifts.
    const stroke = (ph: number) => { const s = Math.sin(ph); return s * (0.8 + 0.2 * Math.abs(s)); };
    const tapL = typing * 0.13 * stroke(k.tap) * (0.8 + 0.2 * Math.sin(k.tap * 0.21 + pose.seed));
    const tapR = typing * 0.13 * stroke(k.tap * 1.07 + 2.1) * (0.8 + 0.2 * Math.sin(k.tap * 0.17 + pose.seed * 1.3));

    if (root.current) root.current.position.y = p[1] + lift;
    if (body.current) {
      body.current.position.y = 0.5 + Math.sin(k.breath * 1.5 + pose.seed) * 0.014;
      body.current.rotation.y = yaw * 0.12;
    }
    if (head.current) { head.current.rotation.set(pitch, yaw, roll); }
    if (armL.current) armL.current.rotation.x = REST + tapL + Math.sin(k.breath * 1.5 + pose.seed) * 0.01;
    if (armR.current) armR.current.rotation.x = REST - tapR + Math.sin(k.breath * 1.5 + pose.seed) * 0.01;
    if (face.current) (face.current.material as MeshStandardMaterial).emissiveIntensity = glow * 0.9;
  });

  return (
    <group ref={root} position={p}>
      <group ref={body} position={[0, 0.5, 0]}>
        <Box p={[0, 0.42, 0]} s={[0.9, 0.84, 0.56]} c={look.shirt} />
        {look.tie && <Box p={[0, 0.5, 0.29]} s={[0.14, 0.52, 0.02]} c={look.tie} shadow={false} />}
        {look.bowtie && <Box p={[0, 0.78, 0.29]} s={[0.32, 0.12, 0.03]} c={look.bowtie} shadow={false} />}
        <Box p={[0, 0.8, 0.27]} s={[0.36, 0.08, 0.02]} c={BOT.collar} shadow={false} />
        <Arm side={-1} shirt={look.shirt} skin={skin} y={0.74} gref={armL} />
        <Arm side={1} shirt={look.shirt} skin={skin} y={0.74} gref={armR} />
        <group ref={head} position={[0, 1.24, 0]}>
          <Box ref={face} s={[0.78, 0.78, 0.78]} c={skin} e="#ffb84a" ei={0} />
          <Hair style={look.hairStyle} c={look.hair} />
          <Box p={[-0.17, 0.03, 0.4]} s={[0.1, 0.14, 0.02]} c={DARK} shadow={false} />
          <Box p={[0.17, 0.03, 0.4]} s={[0.1, 0.14, 0.02]} c={DARK} shadow={false} />
          <Box p={[0, -0.2, 0.4]} s={[0.22, 0.05, 0.02]} c={BOT.mouth} shadow={false} />
          {look.glasses && <Glasses />}
        </group>
      </group>
    </group>
  );
}
