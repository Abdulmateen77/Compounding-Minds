import type { Lens } from "../research";
import { BOT, lookFor } from "../scene/theme";

/* The investor's face, drawn from the same character as the 3D bot in the office, so a card and the person at the desk are plainly the
   same investor.

   Every number below is the size of a box in scene/Analyst.tsx, seen from the front, in scene units, measured from the centre of the head
   (x to the right, y up). The head is a 0.78 cube, the body 0.9 wide, and the head sits 1.24 above the body's base. Colours come from the
   investor's own look (scene/theme.ts) and the shared parts (BOT), so changing a bot changes its icon. */

const VIEW = { x: -0.65, top: 0.6, size: 1.3 };           // the part of the bot the icon shows: the head, collar and top of the shirt

/** A box given by its centre and size, flipped into SVG's downward y. */
const Box = ({ x, y, w, h, c, o }: { x: number; y: number; w: number; h: number; c: string; o?: number }) =>
  <rect x={x - w / 2} y={-(y + h / 2)} width={w} height={h} fill={c} opacity={o} />;

/** The shirt a little darker, for the sleeves, which sit behind the body in the 3D bot. */
const darken = (hex: string, by: number) => {
  const n = parseInt(hex.slice(1), 16), f = (v: number) => Math.round(v * (1 - by)).toString(16).padStart(2, "0");
  return `#${f((n >> 16) & 255)}${f((n >> 8) & 255)}${f(n & 255)}`;
};

function Hair({ style, c }: { style?: string; c: string }) {
  if (style === "bald") return <><Box x={-0.4} y={0.02} w={0.06} h={0.28} c={c} /><Box x={0.4} y={0.02} w={0.06} h={0.28} c={c} /></>;
  return (
    <>
      <Box x={0} y={0.44} w={0.84} h={0.16} c={c} />
      {style === "side" && <><Box x={-0.41} y={0.15} w={0.06} h={0.45} c={c} /><Box x={0.41} y={0.15} w={0.06} h={0.45} c={c} /></>}
      {style === "swoop" && <Box x={-0.12} y={0.33} w={0.6} h={0.12} c={c} />}
    </>
  );
}

export function Avatar({ l, size = 40, ring }: { l: Lens; size?: number; ring?: string }) {
  const k = lookFor(l.key, l.key), skin = k.skin ?? BOT.skin;   // by key, exactly as the 3D scene does: the full name ("Warren Buffett") matches no look
  return (
    <svg width={size} height={size} viewBox={`${VIEW.x} ${-VIEW.top} ${VIEW.size} ${VIEW.size}`} aria-hidden className="shrink-0 rounded-full"
      style={{ background: BOT.wall, boxShadow: ring ? `0 0 0 2px ${ring}` : undefined }}>
      {/* body and sleeves */}
      <Box x={0} y={-0.82} w={0.9} h={0.84} c={k.shirt} />
      <Box x={-0.56} y={-0.64} w={0.22} h={0.3} c={darken(k.shirt, 0.22)} />
      <Box x={0.56} y={-0.64} w={0.22} h={0.3} c={darken(k.shirt, 0.22)} />
      {/* collar, tie or bow tie */}
      <Box x={0} y={-0.44} w={0.36} h={0.08} c={BOT.collar} />
      {k.tie && <Box x={0} y={-0.74} w={0.14} h={0.52} c={k.tie} />}
      {k.bowtie && <Box x={0} y={-0.46} w={0.32} h={0.12} c={k.bowtie} />}
      {/* the head's shadow on the shirt, then the head */}
      <Box x={0} y={-0.43} w={0.78} h={0.08} c="#000" o={0.22} />
      <Box x={0} y={0} w={0.78} h={0.78} c={skin} />
      <Hair style={k.hairStyle} c={k.hair} />
      {/* face: eyes, mouth, and the frames when they wear glasses */}
      <Box x={-0.17} y={0.03} w={0.1} h={0.14} c={BOT.ink} />
      <Box x={0.17} y={0.03} w={0.1} h={0.14} c={BOT.ink} />
      <Box x={0} y={-0.2} w={0.22} h={0.05} c={BOT.mouth} />
      {k.glasses && [-0.17, 0.17].map((x) => (
        <g key={x}>
          <Box x={x} y={0.13} w={0.26} h={0.04} c={BOT.ink} /><Box x={x} y={-0.07} w={0.26} h={0.04} c={BOT.ink} />
          <Box x={x - 0.11} y={0.03} w={0.04} h={0.2} c={BOT.ink} /><Box x={x + 0.11} y={0.03} w={0.04} h={0.2} c={BOT.ink} />
        </g>
      ))}
      {k.glasses && <Box x={0} y={0.09} w={0.1} h={0.03} c={BOT.ink} />}
    </svg>
  );
}
