import type { Lens } from "../research";
import { lookFor } from "../scene/theme";

/** The investor's face, drawn from the same look as their character in the 3D office (hair, glasses, shirt and tie), so the
    cards and the scene match. */
export function Avatar({ l, size = 40, ring }: { l: Lens; size?: number; ring?: string }) {
  const k = lookFor(l.name, l.key), skin = k.skin ?? "#f1c7a0", ink = "#1d1d2b";
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" shapeRendering="crispEdges" aria-hidden className="shrink-0 rounded-full"
      style={{ background: "#1f2647", boxShadow: ring ? `0 0 0 2px ${ring}` : undefined }}>
      <rect x="2" y="13" width="12" height="3" fill={k.shirt} />
      {k.tie && <rect x="7.3" y="13" width="1.4" height="3" fill={k.tie} />}
      {k.bowtie && <rect x="6.5" y="13" width="3" height="1" fill={k.bowtie} />}
      <rect x="4" y="4" width="8" height="9" fill={skin} />
      {k.hairStyle === "bald" ? (
        <><rect x="4" y="5" width="1" height="3" fill={k.hair} /><rect x="11" y="5" width="1" height="3" fill={k.hair} /></>
      ) : k.hairStyle === "swoop" ? (
        <><rect x="3.5" y="2.5" width="9" height="2.5" fill={k.hair} /><rect x="8.5" y="5" width="3.5" height="1" fill={k.hair} /></>
      ) : k.hairStyle === "side" ? (
        <><rect x="4" y="3" width="8" height="2" fill={k.hair} /><rect x="4" y="5" width="1.5" height="2" fill={k.hair} /></>
      ) : (
        <rect x="4" y="3" width="8" height="2" fill={k.hair} />
      )}
      <rect x="6" y="8" width="1" height="1.2" fill={ink} />
      <rect x="9" y="8" width="1" height="1.2" fill={ink} />
      {k.glasses && (
        <g fill="none" stroke={ink} strokeWidth="0.45">
          <rect x="5.2" y="7.3" width="2.6" height="2.2" /><rect x="8.2" y="7.3" width="2.6" height="2.2" />
        </g>
      )}
      <rect x="7" y="11" width="2" height="0.6" fill="#b5735a" />
    </svg>
  );
}
