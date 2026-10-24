import React from 'react';
import {Box} from './Box';

type V3 = [number, number, number];

export type Look = {
  shirt: string;
  hair: string;
  skin?: string;
  tie?: string;
  bowtie?: string;
  glasses?: boolean;
  hairStyle?: 'flat' | 'side' | 'bald' | 'swoop';
};

export type Pose = {
  t?: number; // frame, drives idle motion
  typing?: number; // 0..1
  headDrop?: number; // 0..1 sad
  headTurn?: number; // radians
  jump?: number; // world units
  armsUp?: number; // 0..1 celebrate
  standing?: boolean;
  glow?: number; // 0..1 lesson glow
};

const DARK = '#1b1b26';
const PANTS = '#2d2f45';

const Glasses: React.FC = () => (
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

const Hair: React.FC<{style: Look['hairStyle']; c: string}> = ({style = 'flat', c}) => {
  if (style === 'bald') {
    return (
      <>
        <Box p={[-0.4, 0.02, -0.05]} s={[0.06, 0.28, 0.55]} c={c} />
        <Box p={[0.4, 0.02, -0.05]} s={[0.06, 0.28, 0.55]} c={c} />
        <Box p={[0, 0.02, -0.4]} s={[0.82, 0.28, 0.06]} c={c} />
      </>
    );
  }
  return (
    <>
      <Box p={[0, 0.44, 0]} s={[0.84, 0.16, 0.84]} c={c} />
      {style === 'side' && (
        <>
          <Box p={[-0.41, 0.15, -0.05]} s={[0.06, 0.45, 0.7]} c={c} />
          <Box p={[0.41, 0.15, -0.05]} s={[0.06, 0.45, 0.7]} c={c} />
          <Box p={[0, 0.15, -0.41]} s={[0.84, 0.5, 0.06]} c={c} />
        </>
      )}
      {style === 'swoop' && <Box p={[-0.12, 0.33, 0.39]} s={[0.6, 0.12, 0.1]} c={c} />}
      {style === 'flat' && <Box p={[0, 0.2, -0.41]} s={[0.84, 0.4, 0.06]} c={c} />}
    </>
  );
};

const Arm: React.FC<{side: -1 | 1; rotX: number; rotZ: number; shirt: string; skin: string; y: number}> = ({
  side,
  rotX,
  rotZ,
  shirt,
  skin,
  y,
}) => (
  <group position={[side * 0.56, y, 0]} rotation={[rotX, 0, rotZ * side]}>
    <Box p={[0, -0.3, 0]} s={[0.22, 0.62, 0.24]} c={shirt} />
    <Box p={[0, -0.68, 0]} s={[0.2, 0.16, 0.2]} c={skin} />
  </group>
);

// A blocky analyst. Origin is the floor point under the character.
export const Analyst: React.FC<{look: Look; pose?: Pose; p?: V3; ry?: number; scale?: number}> = ({
  look,
  pose = {},
  p = [0, 0, 0],
  ry = 0,
  scale = 1,
}) => {
  const {t = 0, typing = 0, headDrop = 0, headTurn = 0, jump = 0, armsUp = 0, standing = false, glow = 0} = pose;
  const skin = look.skin ?? '#f1c7a0';
  const base = standing ? 0.62 : 0.5;
  const breathe = Math.sin(t * 0.12) * 0.015;

  // Arms: hanging (standing) or reaching to the keyboard (seated), blended to straight up.
  const restX = standing ? 0 : -1.15;
  const tap = typing * Math.sin(t * 0.9) * 0.12;
  const rotX = (1 - armsUp) * (restX + tap) + armsUp * -Math.PI * 0.92;
  const rotZ = standing ? 0.08 + armsUp * 0.3 : armsUp * 0.3;

  if (scale <= 0.001) return null;
  return (
    <group position={[p[0], p[1] + jump, p[2]]} rotation={[0, ry, 0]} scale={scale}>
      {standing && (
        <>
          <Box p={[-0.2, 0.31, 0]} s={[0.3, 0.62, 0.36]} c={PANTS} />
          <Box p={[0.2, 0.31, 0]} s={[0.3, 0.62, 0.36]} c={PANTS} />
        </>
      )}
      <group position={[0, base + breathe, 0]}>
        <Box p={[0, 0.42, 0]} s={[0.9, 0.84, 0.56]} c={look.shirt} />
        {look.tie && <Box p={[0, 0.5, 0.29]} s={[0.14, 0.52, 0.02]} c={look.tie} shadow={false} />}
        {look.bowtie && <Box p={[0, 0.78, 0.29]} s={[0.32, 0.12, 0.03]} c={look.bowtie} shadow={false} />}
        <Box p={[0, 0.8, 0.27]} s={[0.36, 0.08, 0.02]} c="#f4f1ea" shadow={false} />
        <Arm side={-1} rotX={rotX} rotZ={rotZ} shirt={look.shirt} skin={skin} y={0.74} />
        <Arm side={1} rotX={rotX + (armsUp > 0 ? 0 : tap * -2)} rotZ={rotZ} shirt={look.shirt} skin={skin} y={0.74} />
        <group position={[0, 1.24, 0]} rotation={[headDrop * 0.5, headTurn, 0]}>
          <Box s={[0.78, 0.78, 0.78]} c={skin} e="#ffb84a" ei={glow * 0.9} />
          <Hair style={look.hairStyle} c={look.hair} />
          <Box p={[-0.17, 0.03 - headDrop * 0.04, 0.4]} s={[0.1, 0.14 - headDrop * 0.08, 0.02]} c={DARK} shadow={false} />
          <Box p={[0.17, 0.03 - headDrop * 0.04, 0.4]} s={[0.1, 0.14 - headDrop * 0.08, 0.02]} c={DARK} shadow={false} />
          <Box p={[0, -0.2, 0.4]} s={[0.22 - armsUp * 0.04, 0.05 + armsUp * 0.06, 0.02]} c="#8a3b35" shadow={false} />
          {look.glasses && <Glasses />}
        </group>
      </group>
    </group>
  );
};
