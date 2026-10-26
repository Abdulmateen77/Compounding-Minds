/** Durations in seconds for framer-motion, matching the CSS tokens --duration-fast, --duration, --duration-slow and --duration-slower. */
export const DUR = { fast: 0.15, base: 0.25, slow: 0.35, slower: 0.5 } as const;

/** The long, gentle ease used for reveals and page changes (the CSS token --ease-soft). */
export const EASE_SOFT = [0.22, 1, 0.36, 1] as const;
