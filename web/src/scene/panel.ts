/** The six investors on the panel, in the order the report gives their lenses. Used only by the loading room, before the report
    (which carries the real list) has arrived; keep it in step with research/analysis.py. */
export const PANEL = [
  { key: "buffett", name: "Warren Buffett" },
  { key: "munger", name: "Charlie Munger" },
  { key: "graham", name: "Benjamin Graham" },
  { key: "lynch", name: "Peter Lynch" },
  { key: "dalio", name: "Ray Dalio" },
  { key: "jhunjhunwala", name: "Rakesh Jhunjhunwala" },
] as const;
