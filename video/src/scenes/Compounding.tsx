import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {Analyst} from '../three/Analyst';
import {Box} from '../three/Box';
import {Label} from '../three/Label';
import {CameraRig, Lights, Room} from '../three/Set';
import {Badge, Caption, TitleTape, Vignette} from '../ui/Overlays';
import {C, SANS, SERIF, SCENES, TEAM, clamp01, easeInOut} from '../theme';

// ILLUSTRATIVE numbers for the video only. Swap in real replay results before showing as results.
const YEARS = ['2018', '2019', '2020', '2021', '2022', '2023', '2024'];
const ACC = [0.55, 0.6, 0.42, 0.62, 0.68, 0.73, 0.78];
const FROZEN = 0.55;
const toH = (a: number) => (a - 0.3) * 7;
const BAR_GAP = 0.85;
// Analysts stand either side of the chart so the bars never hide them.
const ANALYST_SPOTS: [number, number, number][] = [
  [3.8, 0, 0.5],
  [-4.75, 0, 0.5],
  [4.85, 0, 0.2],
  [-5.8, 0, 0.2],
];

const barColor = (i: number) => (i === 2 ? C.red : i < 2 ? C.amber : C.green);

const EndCard: React.FC<{start: number}> = ({start}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const dim = interpolate(f, [start, start + 12], [0, 0.78], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const pop = spring({frame: f - start - 6, fps, config: {damping: 12, stiffness: 140}});
  const sub = spring({frame: f - start - 16, fps, config: {damping: 14, stiffness: 140}});
  if (f < start) return null;
  return (
    <AbsoluteFill style={{background: `rgba(10, 13, 32, ${dim})`, alignItems: 'center', justifyContent: 'center'}}>
      <div style={{textAlign: 'center', transform: `scale(${0.7 + 0.3 * pop})`, opacity: Math.min(1, pop * 1.4)}}>
        <div style={{fontFamily: SANS, fontWeight: 900, fontSize: 132, color: C.paper, letterSpacing: 4}}>
          COMPOUNDING MINDS
        </div>
        <div
          style={{
            fontFamily: SERIF,
            fontStyle: 'italic',
            fontWeight: 700,
            fontSize: 52,
            color: C.amber,
            marginTop: 18,
            opacity: sub,
            transform: `translateY(${(1 - sub) * 20}px)`,
          }}
        >
          AI analysts that get better every time they're wrong
        </div>
        <div
          style={{
            fontFamily: SANS,
            fontWeight: 700,
            fontSize: 30,
            color: '#c9c3ff',
            letterSpacing: 6,
            marginTop: 34,
            opacity: sub,
          }}
        >
          POWERED BY MUBIT
        </div>
      </div>
    </AbsoluteFill>
  );
};

// Scene 4: accuracy by year, COVID dip, learned agents beat their frozen twin.
export const Compounding: React.FC = () => {
  const f = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();

  const t = easeInOut(clamp01(f / SCENES.chart));
  const angle = -0.32 + t * 0.5;
  const r = 13 - t * 1.2;
  const cam: [number, number, number] = [Math.sin(angle) * r, 3.4 + t * 0.4, Math.cos(angle) * r];

  const line = spring({frame: f - 112, fps, config: {damping: 14, stiffness: 120}});
  const covid = spring({frame: f - 66, fps, config: {damping: 10, stiffness: 160}});
  const cheerStart = 140;

  return (
    <AbsoluteFill>
      <ThreeCanvas width={width} height={height} shadows camera={{fov: 35, position: cam}}>
        <CameraRig pos={cam} look={[0, 1.7, -0.3]} />
        <Lights />
        <Room wallZ={-4} />
        {/* platform */}
        <Box p={[0, 0.15, 0]} s={[6.8, 0.3, 2.0]} c="#2a3160" />
        <Box p={[0, 0.31, 0]} s={[6.6, 0.02, 1.8]} c="#343d75" />
        {YEARS.map((y, i) => {
          const x = (i - 3) * BAR_GAP;
          const grow = spring({frame: f - 14 - i * 9, fps, config: {damping: 13, stiffness: 110}});
          const h = Math.max(0.001, toH(ACC[i]) * grow);
          return (
            <group key={y}>
              <Box p={[x, 0.32 + h / 2, 0]} s={[0.62, h, 0.62]} c={barColor(i)} rough={0.55} />
              <Label
                width={0.7}
                p={[x, 0.15, 1.01]}
                spec={{w: 220, h: 80, lines: [{text: y, size: 58, weight: 900, color: C.paper}]}}
              />
              <Label
                width={0.62}
                p={[x, 0.32 + h + 0.22, 0]}
                opacity={clamp01(grow * 3 - 2)}
                spec={{w: 220, h: 90, lines: [{text: `${Math.round(ACC[i] * 100)}%`, size: 62, weight: 900, color: C.paper}]}}
              />
            </group>
          );
        })}
        <Label
          width={1.1}
          p={[-1 * BAR_GAP, 0.32 + toH(ACC[2]) + 0.62, 0]}
          scale={covid}
          spec={{w: 340, h: 110, bg: C.red, radius: 55, lines: [{text: 'COVID', size: 60, weight: 900, color: '#fff', spacing: 4}]}}
        />
        {/* frozen twin: the same agents with no learning */}
        <group scale={[line, 1, 1]} position={[0, 0.32 + toH(FROZEN), 0.38]}>
          <Box s={[6.0, 0.05, 0.05]} c={C.grey} e={C.grey} ei={0.4} shadow={false} />
        </group>
        <Label
          width={1.3}
          p={[-3.85, 0.32 + toH(FROZEN), 0.5]}
          scale={line}
          spec={{w: 480, h: 110, bg: '#5b6180', radius: 55, lines: [{text: 'FROZEN TWIN', size: 50, weight: 900, color: '#fff', spacing: 3}]}}
        />
        {TEAM.map((m, i) => {
          const local = f - cheerStart - i * 4;
          const hop = local > 0 ? Math.abs(Math.sin(local * 0.3)) * 0.55 : 0;
          return (
            <Analyst
              key={m.name}
              look={m.look}
              p={ANALYST_SPOTS[i]}
              ry={ANALYST_SPOTS[i][0] > 0 ? -0.35 : 0.35}
              pose={{t: f + i * 13, standing: true, armsUp: clamp01(local / 8), jump: hop, headTurn: Math.sin((f + i * 30) * 0.05) * 0.2}}
            />
          );
        })}
      </ThreeCanvas>
      <Vignette />
      <Badge text="ILLUSTRATIVE DATA" start={20} />
      <TitleTape text="ACCURACY COMPOUNDS" start={4} end={168} />
      <Caption words={['crashes', 'in', '2020,', 'then', 'learns', 'its', 'way', 'back']} start={70} perWord={4} end={168} />
      <EndCard start={172} />
    </AbsoluteFill>
  );
};
