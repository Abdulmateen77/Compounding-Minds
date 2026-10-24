import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "./api/client";
import Select from "./screens/Select";
import Run from "./screens/Run";
import Verdict from "./screens/Verdict";

type Phase = { name: "select" } | { name: "run"; id: string } | { name: "verdict"; id: string };

export default function App() {
  const [phase, setPhase] = useState<Phase>({ name: "select" });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });

  return (
    <div className="min-h-screen flex flex-col">
      {health.data?.banner && (
        <div className="text-center text-xs py-2 px-4" style={{ background: "color-mix(in srgb, var(--amber) 16%, transparent)", color: "var(--amber)", borderBottom: "1px solid var(--line)" }}>
          {health.data.banner}
        </div>
      )}
      <header className="max-w-5xl w-full mx-auto px-4 pt-6 pb-2 flex items-center justify-between">
        <button className="flex items-center gap-2 font-semibold tracking-tight cursor-pointer bg-transparent border-0" style={{ color: "var(--text)" }} onClick={() => setPhase({ name: "select" })}>
          <span className="inline-block w-6 h-6 rounded-md" style={{ background: "linear-gradient(135deg,var(--blue),var(--purple))" }} />
          Compounding Minds
        </button>
        <span className="chip">{health.data ? `${health.data.companies} companies · replay mode` : "connecting…"}</span>
      </header>
      <main className="max-w-5xl w-full mx-auto px-4 py-6 flex-1">
        <AnimatePresence mode="wait">
          <motion.div key={phase.name} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
            {phase.name === "select" && <Select onStart={(id) => setPhase({ name: "run", id })} />}
            {phase.name === "run" && <Run id={phase.id} onDone={() => setPhase({ name: "verdict", id: phase.id })} onBack={() => setPhase({ name: "select" })} />}
            {phase.name === "verdict" && <Verdict id={phase.id} onBack={() => setPhase({ name: "select" })} />}
          </motion.div>
        </AnimatePresence>
      </main>
      <footer className="text-center text-xs mute py-6">Research tool, not financial advice. Assessments describe business evidence in filings, not investment advice or a recommendation to trade.</footer>
    </div>
  );
}
