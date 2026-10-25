import { motion } from "framer-motion";

export function Ring({ value, color, size = 132 }: { value: number; color: string; size?: number }) {
  const r = size / 2 - 10, c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} role="img" aria-label={`Confidence ${Math.round(value * 100)} percent`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth="9" />
      <motion.circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="9" strokeLinecap="round"
        strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - value) }}
        transition={{ duration: 1.1, ease: "easeOut" }} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" fill="var(--text)" fontSize="26" fontWeight="700" className="num">
        {Math.round(value * 100)}%
      </text>
    </svg>
  );
}

export function Spark({ data, color = "var(--blue)", w = 120, h = 34 }: { data: number[]; color?: string; w?: number; h?: number }) {
  if (data.length < 2) return <span className="mute text-xs">n/a</span>;
  const lo = Math.min(...data), hi = Math.max(...data), span = hi - lo || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * (w - 4) + 2},${h - 3 - ((v - lo) / span) * (h - 6)}`).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ maxWidth: "100%", height: "auto" }} aria-hidden>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts.split(" ").pop()!.split(",")[0]} cy={pts.split(" ").pop()!.split(",")[1]} r="3" fill={color} />
    </svg>
  );
}

export function VoteBar({ for_, neutral, against }: { for_: number; neutral: number; against: number }) {
  const total = for_ + neutral + against || 1;
  const seg = (n: number, color: string) => n > 0 && <motion.div initial={{ flex: 0 }} animate={{ flex: n / total }} transition={{ duration: 0.8 }} style={{ background: color }} />;
  return (
    <div>
      <div className="flex h-3 rounded-full overflow-hidden" style={{ background: "var(--line)" }}>
        {seg(for_, "var(--green)")}{seg(neutral, "var(--amber)")}{seg(against, "var(--red)")}
      </div>
      <div className="flex gap-4 mt-2 text-xs mute num">
        <span style={{ color: "var(--green)" }}>{for_} for</span><span style={{ color: "var(--amber)" }}>{neutral} neutral</span><span style={{ color: "var(--red)" }}>{against} against</span>
      </div>
    </div>
  );
}

export function fmt(v: number, unit?: string | null) {
  if (unit === "ratio") return `${(v * 100).toFixed(1)}%`;
  if (Math.abs(v) >= 100) return v.toFixed(0);
  return Math.abs(v) < 1 ? v.toFixed(3) : v.toFixed(2);
}

export function Revision({ from, to }: { from?: number | null; to: number }) {
  if (from == null || Math.abs(from - to) < 0.005) return null;
  const up = to > from;
  return (
    <span className="chip num" title="Confidence after cross-examination" style={{ color: up ? "var(--green)" : "var(--amber)", borderColor: "currentColor" }}>
      {Math.round(from * 100)}% {up ? "\u2197" : "\u2198"} {Math.round(to * 100)}%
    </span>
  );
}

export function Skeleton({ h = 120, className = "" }: { h?: number; className?: string }) {
  return <div className={`card animate-pulse ${className}`} style={{ height: h, opacity: 0.6 }} aria-hidden />;
}

export function ErrorBox({ msg, onRetry }: { msg: string; onRetry?: () => void }) {
  return (
    <div className="card p-5" role="alert" style={{ borderColor: "var(--red)" }}>
      <div style={{ color: "var(--red)" }} className="font-semibold">Something went wrong</div>
      <p className="mute text-sm my-2">{msg}</p>
      {onRetry && <button className="btn ghost" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function StubChip() {
  return <span className="chip" style={{ color: "var(--amber)", borderColor: "var(--amber)" }}>NOT RESULTS</span>;
}

/** Two-series sparkline: learned (accent) over frozen (muted baseline). */
export function Spark2({ learned, frozen, w = 220, h = 56 }: { learned: number[]; frozen: number[]; w?: number; h?: number }) {
  const all = [...learned, ...frozen];
  if (learned.length < 2) return <span className="mute text-xs">not enough history</span>;
  const lo = Math.min(...all), hi = Math.max(...all), span = hi - lo || 1;
  const line = (d: number[]) => d.map((v, i) => `${(i / Math.max(d.length - 1, 1)) * (w - 6) + 3},${h - 4 - ((v - lo) / span) * (h - 8)}`).join(" ");
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ maxWidth: w }} role="img" aria-label="Rolling accuracy, learned versus frozen">
      {frozen.length > 1 && <polyline points={line(frozen)} fill="none" stroke="var(--mute)" strokeWidth="1.5" strokeDasharray="4 3" />}
      <motion.polyline points={line(learned)} fill="none" stroke="var(--green)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1 }} />
    </svg>
  );
}
