import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { Group, Mesh, MeshStandardMaterial } from "three";
import { Box } from "./Box";
import type { Look } from "./theme";

type V3 = [number, number, number];

/** Animated values, recomputed each frame by the caller from the director clock. */
export type Pose = { t: number; typing: number; headTurn: number; jump: number; glow: number };

const DARK = "#1b1b26";

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
  <group ref={gref} position={[side * 0.56, y, 0]} rotation={[-1.15, 0, 0]}>
    <Box p={[0, -0.3, 0]} s={[0.22, 0.62, 0.24]} c={shirt} />
    <Box p={[0, -0.68, 0]} s={[0.2, 0.16, 0.2]} c={skin} />
  </group>
);

/** A seated blocky analyst. Origin is the floor point under the character. Animated imperatively (no re-render per frame). */
export function Analyst({ look, getPose, p = [0, 0, 0] }: { look: Look; getPose: () => Pose; p?: V3 }) {
  const skin = look.skin ?? "#f1c7a0";
  const root = useRef<Group>(null), body = useRef<Group>(null), head = useRef<Group>(null);
  const armL = useRef<Group>(null), armR = useRef<Group>(null), face = useRef<Mesh>(null);

  useFrame(() => {
    const { t, typing, headTurn, jump, glow } = getPose();
    const tap = typing * Math.sin(t * 0.9) * 0.12;
    if (root.current) root.current.position.y = p[1] + jump;
    if (body.current) body.current.position.y = 0.5 + Math.sin(t * 0.12) * 0.015;
    if (head.current) head.current.rotation.y = headTurn;
    if (armL.current) armL.current.rotation.x = -1.15 + tap;
    if (armR.current) armR.current.rotation.x = -1.15 - tap;
    if (face.current) (face.current.material as MeshStandardMaterial).emissiveIntensity = glow * 0.9;
  });

  return (
    <group ref={root} position={p}>
      <group ref={body} position={[0, 0.5, 0]}>
        <Box p={[0, 0.42, 0]} s={[0.9, 0.84, 0.56]} c={look.shirt} />
        {look.tie && <Box p={[0, 0.5, 0.29]} s={[0.14, 0.52, 0.02]} c={look.tie} shadow={false} />}
        {look.bowtie && <Box p={[0, 0.78, 0.29]} s={[0.32, 0.12, 0.03]} c={look.bowtie} shadow={false} />}
        <Box p={[0, 0.8, 0.27]} s={[0.36, 0.08, 0.02]} c="#f4f1ea" shadow={false} />
        <Arm side={-1} shirt={look.shirt} skin={skin} y={0.74} gref={armL} />
        <Arm side={1} shirt={look.shirt} skin={skin} y={0.74} gref={armR} />
        <group ref={head} position={[0, 1.24, 0]}>
          <Box ref={face} s={[0.78, 0.78, 0.78]} c={skin} e="#ffb84a" ei={0} />
          <Hair style={look.hairStyle} c={look.hair} />
          <Box p={[-0.17, 0.03, 0.4]} s={[0.1, 0.14, 0.02]} c={DARK} shadow={false} />
          <Box p={[0.17, 0.03, 0.4]} s={[0.1, 0.14, 0.02]} c={DARK} shadow={false} />
          <Box p={[0, -0.2, 0.4]} s={[0.22, 0.05, 0.02]} c="#8a3b35" shadow={false} />
          {look.glasses && <Glasses />}
        </group>
      </group>
    </group>
  );
}
