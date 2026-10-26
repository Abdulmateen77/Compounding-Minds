import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {Analyst} from '../three/Analyst';
import {Box} from '../three/Box';
import {Label} from '../three/Label';
import {CameraRig, Lights, Room} from '../three/Set';
import {Badge, Caption, TitleTape, Vignette} from '../ui/Overlays';
import {C, SANS, SERIF, SCENES, TEAM, clamp01, easeInOut} from '../theme';

// Real held-out results, 2023-2024 (eval/reports/heldout_report.md). Accuracy, higher is better.
type Bar = {v: number; kind: 'naive' | 'learned' | 'frozen'} | null;
const BARS: Bar[] = [
  {v: 0.515, kind: 'naive'}, // scenarios: always "base"
  {v: 0.579, kind: 'learned'},
  {v: 0.638, kind: 'frozen'},
  null,
  {v: 0.4, kind: 'naive'}, // fundamentals: always "yes"
  {v: 0.58, kind: 'learned'},
  {v: 0.6, kind: 'frozen'},
  {v: 0.6, kind: 'naive'}, // fundamentals: base rate
];
const toH = (a: number) => (a - 0.3) * 7;
const BAR_GAP = 0.85;
const slotX = (i: number) => (i - 3.5) * BAR_GAP;
const KIND_COLOR = {naive: C.grey, learned: C.violet, frozen: C.amber};
// Analysts stand either side of the chart so the bars never hide them.
const ANALYST_SPOTS: [number, number, number][] = [
  [3.8, 0, 0.5],
  [-4.75, 0, 0.5],
  [4.85, 0, 0.2],
  [-5.8, 0, 0.2],
];

const Legend: React.FC<{start: number}> = ({start}) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [start, start + 12], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const items: [string, string][] = [
    ['Naive baseline', C.grey],
    ['Learned analyst', C.violet],
    ['Frozen twin', C.amber],
  ];
  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'flex-start', paddingTop: 215, opacity: o}}>
      <div style={{display: 'flex', gap: 28}}>
        {items.map(([t, c]) => (
          <div key={t} style={{display: 'flex', alignItems: 'center', gap: 12, fontFamily: SANS, fontWeight: 800, fontSize: 30, color: C.paper}}>
            <span style={{width: 26, height: 26, borderRadius: 6, background: c, display: 'inline-block'}} />
            {t}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

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
          AI analysts graded against what really happened
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

// Scene 4: the real held-out scoreboard, shown as it came out.
export const Compounding: React.FC = () => {
  const f = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();

  const t = easeInOut(clamp01(f / SCENES.chart));
  const angle = -0.32 + t * 0.5;
  const r = 13 - t * 1.2;
  const cam: [number, number, number] = [Math.sin(angle) * r, 3.4 + t * 0.4, Math.cos(angle) * r];


  return (
    <AbsoluteFill>
      <ThreeCanvas width={width} height={height} shadows camera={{fov: 35, position: cam}}>
        <CameraRig pos={cam} look={[0, 1.7, -0.3]} />
        <Lights />
        <Room wallZ={-4} />
        {/* platform */}
        <Box p={[0, 0.15, 0]} s={[6.8, 0.3, 2.0]} c="#2a3160" />
        <Box p={[0, 0.31, 0]} s={[6.6, 0.02, 1.8]} c="#343d75" />
        {BARS.map((bar, i) => {
          if (!bar) return null;
          const x = slotX(i);
          const grow = spring({frame: f - 14 - i * 9, fps, config: {damping: 13, stiffness: 110}});
          const h = Math.max(0.001, toH(bar.v) * grow);
          return (
            <group key={i}>
              <Box p={[x, 0.32 + h / 2, 0]} s={[0.62, h, 0.62]} c={KIND_COLOR[bar.kind]} rough={0.55} />
              <Label
                width={0.7}
                p={[x, 0.32 + h + 0.22, 0]}
                opacity={clamp01(grow * 3 - 2)}
                spec={{w: 260, h: 90, lines: [{text: `${(bar.v * 100).toFixed(1)}%`, size: 54, weight: 900, color: C.paper}]}}
              />
            </group>
          );
        })}
        <Label
          width={2.4}
          p={[slotX(1), 0.15, 1.01]}
          spec={{w: 700, h: 80, lines: [{text: 'NEXT-YEAR REVENUE', size: 44, weight: 900, color: C.paper, spacing: 2}]}}
        />
        <Label
          width={3.0}
          p={[(slotX(4) + slotX(7)) / 2, 0.15, 1.01]}
          spec={{w: 900, h: 80, lines: [{text: 'FREE-CASH-FLOW MARGIN', size: 44, weight: 900, color: C.paper, spacing: 2}]}}
        />
        {TEAM.map((m, i) => (
          <Analyst
            key={m.name}
            look={m.look}
            p={ANALYST_SPOTS[i]}
            ry={ANALYST_SPOTS[i][0] > 0 ? -0.35 : 0.35}
            pose={{t: f + i * 13, standing: true, headTurn: Math.sin((f + i * 30) * 0.05) * 0.2}}
          />
        ))}
      </ThreeCanvas>
      <Vignette />
      <Badge text="2023-24 HELD-OUT" start={20} />
      <TitleTape text="THE REAL SCORES" start={4} end={168} />
      <Legend start={90} />
      <Caption words={['unseen', 'years,', 'real', 'filings,', 'the', 'twin', 'still', 'wins']} start={70} perWord={4} end={168} />
      <EndCard start={172} />
    </AbsoluteFill>
  );
};
