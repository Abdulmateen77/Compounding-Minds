import React from 'react';
import {AbsoluteFill, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {Analyst} from '../three/Analyst';
import {CameraRig, Desk, Lights, Partition, Room} from '../three/Set';
import {Caption, TitleTape, Vignette} from '../ui/Overlays';
import {SCENES, TEAM, clamp01, easeInOut, lerp3} from '../theme';

const XS = [-3.3, -1.1, 1.1, 3.3];

// Scene 1: the team of four analysts at their desks.
export const Office: React.FC = () => {
  const f = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const t = easeInOut(clamp01(f / SCENES.office));
  const cam = lerp3([0.8, 3.6, 11.5], [-0.4, 2.9, 8.6], t);

  return (
    <AbsoluteFill>
      <ThreeCanvas width={width} height={height} shadows camera={{fov: 35, position: cam}}>
        <CameraRig pos={cam} look={[0, 1.15, -0.4]} />
        <Lights />
        <Room />
        {[-2.2, 0, 2.2].map((x) => (
          <Partition key={x} x={x} />
        ))}
        {TEAM.map((m, i) => {
          const pop = spring({frame: f - 6 - i * 6, fps, config: {damping: 10, stiffness: 140}});
          return (
            <group key={m.name}>
              <Desk p={[XS[i], 0, 0]} name={m.name} role={m.role} />
              <Analyst
                look={m.look}
                p={[XS[i], 0, -0.75]}
                scale={pop}
                pose={{t: f + i * 17, typing: 1, headTurn: Math.sin((f + i * 40) * 0.04) * 0.18}}
              />
            </group>
          );
        })}
      </ThreeCanvas>
      <Vignette />
      <TitleTape text="COMPOUNDING MINDS" start={10} />
      <Caption words={['AI', 'analysts', 'that', 'grade', 'themselves', 'against', 'reality']} start={42} />
    </AbsoluteFill>
  );
};
