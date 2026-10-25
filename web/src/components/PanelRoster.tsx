import { motion } from "framer-motion";
import { DUR, EASE_SOFT } from "../motion";
import { useReducedMotion } from "../route";
import { Avatar } from "./Avatar";
import { lookFor } from "../scene/theme";

/* The five investors on the landing page, drawn as the same bots that sit at the desks in the 3D office, each under a name plate.
   Names and one-line approaches here are labels, not figures; the checks they run are in the report itself. */

const PANEL = [
  { key: "buffett", name: "Warren Buffett", role: "Durable business, real cash" },
  { key: "munger", name: "Charlie Munger", role: "How could it fail?" },
  { key: "lynch", name: "Peter Lynch", role: "What kind of stock, fair price?" },
  { key: "dalio", name: "Ray Dalio", role: "The cycle and the range" },
  { key: "jhunjhunwala", name: "Rakesh Jhunjhunwala", role: "Growth with honest leaders" },
] as const;

export function PanelRoster() {
  const still = useReducedMotion();
  return (
    <section aria-label="The investor panel" className="grid gap-4">
      <div className="max-w-2xl grid gap-1">
        <h2 className="text-xl md:text-2xl font-semibold m-0">Five investors read every company</h2>
        <p className="m-0 mute text-sm leading-relaxed">Each applies their own rules to the same filings, then they face off where they disagree. Open any company to watch them work in the 3D office.</p>
      </div>
      <ul className="m-0 p-0 list-none grid gap-3 grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
        {PANEL.map((p, i) => {
          const k = lookFor(p.key, p.key);
          return (
            <motion.li key={p.key} className="grid" initial={still ? false : { opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: DUR.slower, ease: EASE_SOFT, delay: still ? 0 : i * 0.07 }}>
              <div className="card grid justify-items-center text-center gap-2 px-3 pt-4 pb-4 overflow-hidden"
                style={{ background: `linear-gradient(180deg, color-mix(in srgb, ${k.shirt} 26%, var(--card)), var(--card) 70%)` }}>
                <span className="chip font-semibold" style={{ color: "var(--foreground)", borderColor: k.shirt, background: `color-mix(in srgb, ${k.shirt} 30%, transparent)` }}>{p.name}</span>
                <motion.div animate={still ? undefined : { y: [0, -5, 0] }} transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut", delay: i * 0.4 }}>
                  <Avatar l={p} size={112} round={false} />
                </motion.div>
                <span className="mute text-xs leading-snug">{p.role}</span>
              </div>
            </motion.li>
          );
        })}
      </ul>
    </section>
  );
}
