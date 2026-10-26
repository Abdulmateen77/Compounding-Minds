import React, {useMemo} from 'react';
import * as THREE from 'three';
import {SANS, SERIF} from '../theme';

type V3 = [number, number, number];

export type Line = {
  text: string;
  size: number;
  weight?: number;
  color?: string;
  serif?: boolean;
  spacing?: number;
};

export type LabelSpec = {
  w: number; // canvas width in px (drawn at 2x)
  h: number;
  bg?: string;
  border?: string;
  borderW?: number;
  radius?: number;
  lines: Line[];
  gap?: number;
  align?: 'center' | 'left';
  pad?: number;
};

const SCALE = 2;

function wrap(ctx: CanvasRenderingContext2D, text: string, max: number): string[] {
  const words = text.split(' ');
  const out: string[] = [];
  let cur = '';
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (ctx.measureText(next).width > max && cur) {
      out.push(cur);
      cur = w;
    } else {
      cur = next;
    }
  }
  if (cur) out.push(cur);
  return out;
}

export function makeLabel(spec: LabelSpec): THREE.CanvasTexture {
  const {w, h, bg, border, borderW = 6, radius = 18, lines, gap = 10, align = 'center', pad = 28} = spec;
  const canvas = document.createElement('canvas');
  canvas.width = w * SCALE;
  canvas.height = h * SCALE;
  const ctx = canvas.getContext('2d')!;
  ctx.scale(SCALE, SCALE);

  if (bg || border) {
    const inset = border ? borderW / 2 : 0;
    ctx.beginPath();
    ctx.roundRect(inset, inset, w - inset * 2, h - inset * 2, radius);
    if (bg) {
      ctx.fillStyle = bg;
      ctx.fill();
    }
    if (border) {
      ctx.lineWidth = borderW;
      ctx.strokeStyle = border;
      ctx.stroke();
    }
  }

  // Lay out wrapped lines, then centre the block vertically.
  const blocks = lines.map((l) => {
    ctx.font = `${l.weight ?? 800} ${l.size}px ${l.serif ? SERIF : SANS}`;
    if (l.spacing) ctx.letterSpacing = `${l.spacing}px`;
    const rows = wrap(ctx, l.text, w - pad * 2);
    ctx.letterSpacing = '0px';
    return {l, rows};
  });
  const total =
    blocks.reduce((sum, b) => sum + b.rows.length * b.l.size * 1.15, 0) + gap * (blocks.length - 1);
  let y = (h - total) / 2;
  ctx.textBaseline = 'top';
  ctx.textAlign = align;
  const x = align === 'center' ? w / 2 : pad;
  for (const {l, rows} of blocks) {
    ctx.font = `${l.weight ?? 800} ${l.size}px ${l.serif ? SERIF : SANS}`;
    ctx.fillStyle = l.color ?? '#1d1d2b';
    ctx.letterSpacing = l.spacing ? `${l.spacing}px` : '0px';
    for (const row of rows) {
      ctx.fillText(row, x, y + l.size * 0.05);
      y += l.size * 1.15;
    }
    y += gap;
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

// A flat card in the 3D scene with drawn text on it. `width` is in world units.
export const Label: React.FC<{
  spec: LabelSpec;
  width: number;
  p?: V3;
  r?: V3;
  scale?: number;
  opacity?: number;
}> = ({spec, width, p = [0, 0, 0], r = [0, 0, 0], scale = 1, opacity = 1}) => {
  const key = JSON.stringify(spec);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const tex = useMemo(() => makeLabel(spec), [key]);
  const height = (width * spec.h) / spec.w;
  if (scale <= 0.001) return null;
  return (
    <mesh position={p} rotation={r} scale={scale}>
      <planeGeometry args={[width, height]} />
      <meshBasicMaterial map={tex} transparent opacity={opacity} toneMapped={false} side={THREE.DoubleSide} />
    </mesh>
  );
};
