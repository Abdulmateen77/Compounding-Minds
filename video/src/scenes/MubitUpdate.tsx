import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {Analyst} from '../three/Analyst';
import {Box} from '../three/Box';
import {Label} from '../three/Label';
import {CameraRig, Desk, Lights, Room} from '../three/Set';
import {Badge, Caption, TitleTape, Vignette} from '../ui/Overlays';
import {C, SCENES, TEAM, clamp01, easeInOut, lerp, lerp3} from '../theme';
import {CALL_CARD} from './TheCall';

type V3 = [number, number, number];

const DESK_X = -2.3;
const MACHINE_X = 2.3;
const HEAD: V3 = [DESK_X, 1.75, -0.75];
const INTAKE: V3 = [MACHINE_X, 2.55, 0];

const tag = (label: string, on: boolean) => ({
  w: 480,
  h: 110,
  bg: on ? C.green : '#5b6180',
  radius: 55,
  lines: [{text: label, size: 50, weight: 900, color: '#ffffff', spacing: 3}],
});

const LESSON = {
  w: 700,
  h: 300,
  bg: C.paper,
  radius: 22,
  lines: [
    {text: 'LESSON', size: 34, weight: 800, color: C.violet, spacing: 4},
    {text: 'Capex/revenue rising 3 quarters running? Discount FCF improvement calls.', size: 42, weight: 800, color: C.ink},
  ],
  gap: 14,
};

// Arc from a to b with a hump of `hump` world units.
const arc = (a: V3, b: V3, t: number, hump: number): V3 => {
  const p = lerp3(a, b, t);
  return [p[0], p[1] + Math.sin(Math.PI * t) * hump, p[2]];
};

const Machine: React.FC<{f: number}> = ({f}) => {
  const busy = clamp01((f - 52) / 6) * (1 - clamp01((f - 96) / 8));
  const glow = 0.6 + busy * (1.6 + Math.sin(f * 0.8) * 0.6);
  const jitter = busy * Math.sin(f * 2.3) * 0.03;
  return (
    <group position={[MACHINE_X + jitter, 0, 0]}>
      <Box p={[0, 1.05, 0]} s={[2.1, 2.1, 1.5]} c={C.violetDark} rough={0.6} />
      <Box p={[0, 2.16, 0]} s={[2.25, 0.14, 1.65]} c="#3b3170" />
      {/* intake slot */}
      <Box p={[0, 2.26, 0]} s={[1.0, 0.08, 0.3]} c="#0c0a1a" />
      {/* glowing strips */}
      <Box p={[0, 0.35, 0.76]} s={[1.8, 0.1, 0.02]} c={C.violet} e={C.violet} ei={glow} shadow={false} />
      <Box p={[0, 1.95, 0.76]} s={[1.8, 0.06, 0.02]} c={C.violet} e={C.violet} ei={glow} shadow={false} />
      {/* status lights */}
      {[-0.6, -0.4, -0.2].map((x, i) => (
        <Box
          key={x}
          p={[x, 0.62, 0.77]}
          s={[0.12, 0.12, 0.03]}
          c={i === 2 ? C.green : C.amber}
          e={i === 2 ? C.green : C.amber}
          ei={busy > 0 && Math.floor(f / 4 + i) % 2 === 0 ? 2 : 0.4}
          shadow={false}
        />
      ))}
      <Label
        width={1.6}
        p={[0, 1.25, 0.77]}
        spec={{
          w: 640,
          h: 240,
          bg: '#120f28',
          radius: 20,
          lines: [
            {text: 'MUBIT', size: 120, weight: 900, color: '#d8ccff', spacing: 12},
            {text: 'RECORDS EVERY CALL', size: 30, weight: 700, color: C.violet, spacing: 6},
          ],
          gap: 0,
        }}
      />
      <pointLight position={[0, 1.4, 1.4]} intensity={busy * 18} color={C.violet} distance={6} />
    </group>
  );
};

// Scene 3: the wrong call flies into Mubit, a lesson flies back, the model goes v1 -> v2.
export const MubitUpdate: React.FC = () => {
  const f = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const buffett = TEAM[0];

  const t = easeInOut(clamp01(f / SCENES.mubit));
  const cam = lerp3([-0.2, 3.3, 10.2], [0.2, 3.0, 9.0], t);

  // card: sits by the analyst, then flies into the machine (frames 14-50)
  const fly = easeInOut(clamp01((f - 14) / 36));
  const cardStart: V3 = [DESK_X + 1.3, 2.4, 0.1];
  const cardPos = arc(cardStart, INTAKE, fly, 1.4);
  const cardScale = fly < 1 ? lerp(1, 0.25, fly) : 0;

  // lesson cube: out of the machine, into the analyst's head (frames 96-128)
  const back = easeInOut(clamp01((f - 96) / 32));
  const cubePos = arc([MACHINE_X, 2.5, 0], HEAD, back, 1.8);
  const cubeOn = f >= 96 && back < 1;

  const lesson = spring({frame: f - 92, fps, config: {damping: 12, stiffness: 140}});
  const upgraded = f >= 130;
  const tagPop = upgraded ? spring({frame: f - 130, fps, config: {damping: 8, stiffness: 220}}) : 1;
  const glow = clamp01((f - 126) / 6) * (1 - clamp01((f - 160) / 16));
  const cheer = clamp01((f - 134) / 8);
  const hop = f > 134 ? Math.abs(Math.sin((f - 134) * 0.32)) * 0.35 * (1 - clamp01((f - 170) / 12)) : 0;
  const sad = 1 - clamp01((f - 128) / 8);

  return (
    <AbsoluteFill>
      <ThreeCanvas width={width} height={height} shadows camera={{fov: 35, position: cam}}>
        <CameraRig pos={cam} look={[0, 1.7, 0]} />
        <Lights />
        <Room />
        <Desk p={[DESK_X, 0, 0]} name={buffett.name} role={buffett.role} />
        <Analyst
          look={buffett.look}
          p={[DESK_X, 0, -0.75]}
          pose={{t: f, typing: 0, headDrop: sad * 0.8, headTurn: 0.25 * (1 - cheer), armsUp: cheer, jump: hop, glow}}
        />
        <Label
          spec={upgraded ? tag('1 LESSON', true) : tag('0 LESSONS', false)}
          width={1.25}
          p={[DESK_X, 3.05 + hop, -0.75]}
          scale={upgraded ? 0.7 + 0.3 * tagPop : 1}
        />
        {cardScale > 0 && (
          <group position={cardPos} rotation={[0, -0.2 + fly * 2.5, fly * 1.2]}>
            <Label spec={CALL_CARD} width={1.6} scale={cardScale} />
            <Label
              spec={{w: 520, h: 180, border: C.red, borderW: 14, radius: 16, lines: [{text: 'WRONG', size: 120, weight: 900, color: C.red, spacing: 10}]}}
              width={0.85}
              p={[0.55 * cardScale, -0.42 * cardScale, 0.02]}
              r={[0, 0, -0.16]}
              scale={cardScale}
            />
          </group>
        )}
        <Machine f={f} />
        {cubeOn && (
          <group position={cubePos} rotation={[f * 0.2, f * 0.25, 0]}>
            <Box s={[0.32, 0.32, 0.32]} c={C.amber} e={C.amber} ei={1.6} shadow={false} />
            <pointLight intensity={6} color={C.amber} distance={3} />
          </group>
        )}
        <Label spec={LESSON} width={2.4} p={[MACHINE_X + 0.1, 3.0, 0.4]} scale={lesson} />
      </ThreeCanvas>
      <Vignette />
      <Badge text="EXAMPLE" start={12} />
      <TitleTape text="EVERY MISS BECOMES A LESSON" start={4} />
      <Caption words={['every', 'call', 'is', 'recorded', 'in', 'Mubit']} start={58} perWord={5} />
    </AbsoluteFill>
  );
};
