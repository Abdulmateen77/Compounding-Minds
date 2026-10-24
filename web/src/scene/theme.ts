// Palette and looks ported from the Remotion explainer (video/src/theme.ts). No Remotion imports.
export const SANS = `"Rubik", "Helvetica Neue", Arial, sans-serif`;
export const SERIF = `Georgia, "Times New Roman", serif`;

export const C = {
  bg: "#121831", wall: "#1f2647", floor: "#5a3d2a", desk: "#c08a55", deskDark: "#8c5d36",
  paper: "#f4ecdc", ink: "#1d1d2b", red: "#e5533d", green: "#36c48a", amber: "#f4b23e",
  violet: "#7b5cff", terracotta: "#c8643c", grey: "#9aa0b5",
};

// Three.js needs real hex values (the UI's CSS variables do not resolve inside WebGL).
export const STANCE_HEX = { for: "#2fd37c", neutral: "#f5b13d", against: "#ff5a67" } as const;
export const LABEL_HEX = { investable: "#2fd37c", watch: "#f5b13d", not_investable: "#ff5a67" } as const;

export type Look = {
  shirt: string; hair: string; skin?: string; tie?: string; bowtie?: string; glasses?: boolean;
  hairStyle?: "flat" | "side" | "bald" | "swoop";
};

const LOOKS: Record<string, Look> = {
  buffett: { shirt: "#2f4b8f", hair: "#dcd7cf", tie: "#d8433a", glasses: true, hairStyle: "swoop" },
  graham: { shirt: "#5c6670", hair: "#8f8f8f", bowtie: "#26263d", hairStyle: "side" },
  munger: { shirt: "#3d3d4f", hair: "#ececec", tie: "#27408b", glasses: true, hairStyle: "bald" },
  dalio: { shirt: "#2b7a78", hair: "#b9b2a6", hairStyle: "flat" },
};
const FALLBACK: Look = { shirt: "#4a4f6a", hair: "#b0aaa0", hairStyle: "flat" };

/** Look by investor name as returned by the API (e.g. "Buffett (moat)"). */
export function lookFor(investor: string, agent: string): Look {
  const key = Object.keys(LOOKS).find((k) => investor.toLowerCase().startsWith(k));
  const base = key ? LOOKS[key] : FALLBACK;
  return agent === "moat" ? { ...base, shirt: "#4a3f8f", tie: "#f4b23e" } : base;
}

export const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
export const easeOutBack = (t: number) => { const c = 1.70158; const x = clamp01(t) - 1; return 1 + (c + 1) * x * x * x + c * x * x; };
