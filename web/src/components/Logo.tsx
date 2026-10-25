/** The brand: a "C" drawn as nested rings that widen outward (compounding) around a single seed dot (a mind).
 *  The tile uses the primary fill so it follows the page tokens; the wordmark is set in the app font. */

export function LogoMark({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={className} aria-hidden focusable="false">
      <rect width="32" height="32" rx="7" fill="var(--primary-solid)" />
      <g fill="none" stroke="var(--on-primary)" strokeLinecap="round">
        <path d="M21.5 8.5 A10 10 0 1 0 21.5 23.5" strokeWidth="2.8" />
        <path d="M19.2 12 A5.6 5.6 0 1 0 19.2 20" strokeWidth="2.2" />
      </g>
      <circle cx="16" cy="16" r="1.9" fill="var(--on-primary)" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={`leading-none tracking-[-0.01em] ${className ?? ""}`} style={{ fontWeight: 700 }}>
      Compounding<span style={{ color: "var(--primary)" }}> Minds</span>
    </span>
  );
}
