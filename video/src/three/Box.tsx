import React from 'react';

type V3 = [number, number, number];

// One voxel-style block. Everything in the scenes is built from these.
export const Box: React.FC<{
  p?: V3;
  s: V3;
  c: string;
  r?: V3;
  e?: string;
  ei?: number;
  rough?: number;
  shadow?: boolean;
}> = ({p = [0, 0, 0], s, c, r = [0, 0, 0], e = '#000000', ei = 0, rough = 0.85, shadow = true}) => (
  <mesh position={p} rotation={r} castShadow={shadow} receiveShadow>
    <boxGeometry args={s} />
    <meshStandardMaterial color={c} emissive={e} emissiveIntensity={ei} roughness={rough} />
  </mesh>
);
