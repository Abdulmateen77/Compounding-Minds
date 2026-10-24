import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {Analyst} from '../three/Analyst';
import {Box} from '../three/Box';
import {Label} from '../three/Label';
import {CameraRig, Desk, Lights, Room} from '../three/Set';
import {Caption, TitleTape, Vignette} from '../ui/Overlays';
import {C, SCENES, TEAM, clamp01, easeInOut, lerp3} from '../theme';

export const CALL_CARD = {
  w: 620,
  h: 330,
  bg: C.paper,
  radius: 22,
  lines: [
    {text: 'THE CALL', size: 34, weight: 800, color: C.terracotta, spacing: 4},
    {text: 'FCF margin up next quarter?', size: 56, weight: 900, color: C.ink},
    {text: 'YES  ·  80% confident', size: 40, weight: 700, color: '#3d5a99'},
  ],
  gap: 12,
};

const FILING = {
  w: 500,
  h: 640,
  bg: '#ffffff',
  radius: 10,
  lines: [
    {text: 'FORM 10-Q', size: 70, weight: 900, color: C.ink, spacing: 3},
    {text: 'filed next quarter', size: 30, weight: 500, color: '#6b6b80'},
    {text: 'FCF margin', size: 44, weight: 700, color: C.ink},
    {text: '▼ DOWN', size: 76, weight: 900, color: C.red},
  ],
  gap: 26,
};

const STAMP = {
  w: 520,
  h: 180,
  border: C.red,
  borderW: 14,
  radius: 16,
  lines: [{text: 'WRONG', size: 120, weight: 900, color: C.red, spacing: 10}],
};

// Scene 2: the Buffett agent makes a call, a real filing arrives, the call is graded wrong.
export const TheCall: React.FC = () => {
  const f = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const buffett = TEAM[0];

  const t = easeInOut(clamp01(f / SCENES.call));
  const cam = lerp3([2.6, 2.6, 6.2], [1.7, 2.35, 5.0], t);

  const card = spring({frame: f - 14, fps, config: {damping: 11, stiffness: 150}});
  const drop = spring({frame: f - 62, fps, config: {damping: 9, stiffness: 120}});
  const filingY = interpolate(drop, [0, 1], [6, 0.95]);
  const stampT = f - 104;
  const stamp = stampT < 0 ? 0 : interpolate(stampT, [0, 6], [2.4, 1], {extrapolateRight: 'clamp'});
  const shake = stampT >= 0 && stampT < 10 ? Math.sin(stampT * 3) * 0.04 * (1 - stampT / 10) : 0;
  const sad = clamp01((f - 112) / 14);

  return (
    <AbsoluteFill>
      <ThreeCanvas width={width} height={height} shadows camera={{fov: 35, position: cam}}>
        <CameraRig pos={cam} look={[0.55 + shake, 1.65, -0.1]} />
        <Lights />
        <Room />
        <Desk name={buffett.name} role={buffett.role} />
        <Analyst
          look={buffett.look}
          p={[0, 0, -0.75]}
          pose={{t: f, typing: f < 100 ? 1 : 0.2, headTurn: interpolate(f, [20, 40], [0, 0.35], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) * (1 - sad), headDrop: sad}}
        />
        {/* the call card floating beside the analyst */}
        <group position={[1.5, 2.2, 0.1]} rotation={[0, -0.2, 0]}>
          <Label spec={CALL_CARD} width={1.6} scale={card} />
          {stamp > 0 && (
            <Label spec={STAMP} width={0.85} p={[0.55, -0.42, 0.02]} r={[0, 0, -0.16]} scale={stamp} />
          )}
        </group>
        {/* the filing drops onto the desk */}
        {f >= 62 && (
          <group position={[0.15, filingY, 0.15]} rotation={[-Math.PI / 2, 0, -0.12]}>
            <Box p={[0, 0, -0.012]} s={[0.78, 1.0, 0.02]} c="#ffffff" />
            <Label spec={FILING} width={0.78} />
          </group>
        )}
      </ThreeCanvas>
      <Vignette />
      <TitleTape text="EVERY CALL GETS GRADED" start={4} />
      <Caption words={['checked', 'against', 'what', 'the', 'SEC', 'filings', 'actually', 'said']} start={68} perWord={4} />
    </AbsoluteFill>
  );
};
