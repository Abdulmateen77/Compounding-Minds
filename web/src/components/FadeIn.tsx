import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { DUR, EASE_SOFT } from "../motion";

/** A block that rises into place the first time it scrolls into view, then stays. Reduced motion renders it still, with no wrapper
    animation at all. The bottom margin is small on purpose: a short block at the very end of a page must still be able to appear. */
export function FadeIn({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  const still = useReducedMotion();
  if (still) return <div className={className}>{children}</div>;
  return (
    <motion.div className={className} initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "0px 0px -40px 0px" }} transition={{ duration: DUR.slower + 0.1, delay, ease: EASE_SOFT }}>
      {children}
    </motion.div>
  );
}
