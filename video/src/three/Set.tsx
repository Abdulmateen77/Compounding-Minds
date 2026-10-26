import React, {useMemo} from 'react';
import {useThree} from '@react-three/fiber';
import * as THREE from 'three';
import {Box} from './Box';
import {Label} from './Label';
import {C} from '../theme';

type V3 = [number, number, number];

// Sets the camera every frame. Remotion re-renders per frame, then advances R3F.
export const CameraRig: React.FC<{pos: V3; look: V3; fov?: number}> = ({pos, look, fov = 35}) => {
  const camera = useThree((s) => s.camera) as THREE.PerspectiveCamera;
  camera.position.set(...pos);
  camera.lookAt(...look);
  if (camera.fov !== fov) {
    camera.fov = fov;
    camera.updateProjectionMatrix();
  }
  return null;
};

export const Lights: React.FC<{key1?: number}> = ({key1 = 2.4}) => (
  <>
    <color attach="background" args={[C.bg]} />
    <hemisphereLight args={['#c9d4ff', '#4a3020', 0.9]} />
    <ambientLight intensity={0.35} color="#ffe7cc" />
    <directionalLight
      position={[5, 9, 7]}
      intensity={key1}
      color="#fff1dd"
      castShadow
      shadow-mapSize-width={2048}
      shadow-mapSize-height={2048}
      shadow-camera-left={-12}
      shadow-camera-right={12}
      shadow-camera-top={12}
      shadow-camera-bottom={-12}
      shadow-bias={-0.0004}
    />
    <pointLight position={[-4, 4, 3]} intensity={12} color="#7b8cff" distance={14} />
  </>
);

// Deterministic PRNG so every render tab draws the same skyline.
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function skylineTexture(): THREE.CanvasTexture {
  const w = 1600;
  const h = 500;
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d')!;
  const sky = ctx.createLinearGradient(0, 0, 0, h);
  sky.addColorStop(0, '#0b1030');
  sky.addColorStop(1, '#27306a');
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, w, h);
  const rnd = mulberry32(7);
  let x = 0;
  while (x < w) {
    const bw = 60 + rnd() * 110;
    const bh = 140 + rnd() * 320;
    ctx.fillStyle = rnd() > 0.5 ? '#161c40' : '#1c2350';
    ctx.fillRect(x, h - bh, bw, bh);
    for (let wy = h - bh + 14; wy < h - 10; wy += 22) {
      for (let wx = x + 10; wx < x + bw - 14; wx += 18) {
        if (rnd() > 0.55) {
          ctx.fillStyle = rnd() > 0.3 ? '#ffd27a' : '#9fb4ff';
          ctx.globalAlpha = 0.55 + rnd() * 0.45;
          ctx.fillRect(wx, wy, 8, 11);
          ctx.globalAlpha = 1;
        }
      }
    }
    x += bw + 6;
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

export const Room: React.FC<{wallZ?: number}> = ({wallZ = -3}) => {
  const sky = useMemo(skylineTexture, []);
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[40, 40]} />
        <meshStandardMaterial color={C.floor} roughness={0.9} />
      </mesh>
      {/* floorboards */}
      {Array.from({length: 16}, (_, i) => (
        <mesh key={i} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.002, -2.8 + i * 0.9]} receiveShadow>
          <planeGeometry args={[40, 0.03]} />
          <meshStandardMaterial color="#47301f" />
        </mesh>
      ))}
      <Box p={[0, 4, wallZ - 0.1]} s={[40, 8, 0.2]} c={C.wall} />
      <mesh position={[0, 3.6, wallZ + 0.02]}>
        <planeGeometry args={[16, 5]} />
        <meshBasicMaterial map={sky} toneMapped={false} />
      </mesh>
      {/* window frame */}
      {[-8, -4, 0, 4, 8].map((x) => (
        <Box key={x} p={[x, 3.6, wallZ + 0.08]} s={[0.16, 5, 0.12]} c="#2c345e" />
      ))}
      <Box p={[0, 6.1, wallZ + 0.08]} s={[16.2, 0.18, 0.14]} c="#2c345e" />
      <Box p={[0, 1.1, wallZ + 0.1]} s={[16.2, 0.18, 0.2]} c="#2c345e" />
    </group>
  );
};

// A desk seen from the front. The analyst sits behind it at z = -0.75.
export const Desk: React.FC<{p?: V3; name?: string; role?: string; color?: string}> = ({
  p = [0, 0, 0],
  name,
  role,
  color = C.desk,
}) => (
  <group position={p}>
    <Box p={[0, 0.82, 0]} s={[1.9, 0.12, 1.05]} c={color} />
    <Box p={[-0.88, 0.4, 0]} s={[0.1, 0.8, 0.95]} c={C.deskDark} />
    <Box p={[0.88, 0.4, 0]} s={[0.1, 0.8, 0.95]} c={C.deskDark} />
    <Box p={[0, 0.46, 0.45]} s={[1.7, 0.6, 0.06]} c={C.deskDark} />
    {/* keyboard, papers, mug */}
    <Box p={[0, 0.9, -0.12]} s={[0.72, 0.04, 0.24]} c="#d9d6cf" />
    <Box p={[-0.6, 0.9, 0.18]} s={[0.42, 0.04, 0.52]} c={C.paper} r={[0, 0.2, 0]} />
    <Box p={[0.66, 0.97, 0.22]} s={[0.14, 0.18, 0.14]} c="#e9e3d6" />
    {name && (
      <Label
        width={1.3}
        p={[0, 0.48, 0.49]}
        spec={{
          w: 520,
          h: 170,
          bg: C.paper,
          radius: 14,
          lines: [
            {text: name, size: 64, weight: 900, color: C.ink, spacing: 2},
            ...(role ? [{text: role, size: 26, weight: 700, color: C.terracotta, spacing: 2}] : []),
          ],
          gap: 4,
        }}
      />
    )}
  </group>
);

export const Partition: React.FC<{x: number; z?: number}> = ({x, z = -0.3}) => (
  <group position={[x, 0, z]}>
    <Box p={[0, 0.75, 0]} s={[0.08, 1.5, 1.6]} c="#3b4577" />
    <Box p={[0, 1.52, 0]} s={[0.12, 0.06, 1.64]} c="#c9cde0" />
  </group>
);
