import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "./api/client";
import { useRoute } from "./route";
import Select from "./screens/Select";
import Run from "./screens/Run";
import Verdict from "./screens/Verdict";
import Mubit from "./screens/Mubit";

export default function App() {
  const route = useRoute();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const onMubit = route.name === "mubit";
  const navStyle = (on: boolean) => ({ color: on ? "var(--text)" : "var(--mute)", borderBottom: `2px solid ${on ? "var(--blue)" : "transparent"}` });

  return (
    <div className="min-h-screen flex flex-col">
      {health.data?.banner && (
        <div role="status" className="text-center text-xs py-2 px-4" style={{ background: "color-mix(in srgb, var(--amber) 16%, transparent)", color: "var(--amber)", borderBottom: "1px solid var(--line)" }}>
          {health.data.banner}
        </div>
      )}
      <header className="max-w-5xl w-full mx-auto px-4 pt-5 pb-2 flex items-center justify-between gap-4 flex-wrap">
        <a href="#/" className="flex items-center gap-2 font-semibold tracking-tight no-underline" style={{ color: "var(--text)" }}>
          <span className="inline-block w-6 h-6 rounded-md" style={{ background: "linear-gradient(135deg,var(--blue),var(--purple))" }} aria-hidden />
          Compounding Minds
        </a>
        <nav aria-label="Pages" className="flex gap-5 text-sm font-medium">
          <a href="#/" aria-current={!onMubit ? "page" : undefined} className="py-1 no-underline" style={navStyle(!onMubit)}>Assess</a>
          <a href="#/mubit" aria-current={onMubit ? "page" : undefined} className="py-1 no-underline" style={navStyle(onMubit)}>Mubit</a>
        </nav>
        <span className="chip hidden sm:inline-flex">{health.data ? `${health.data.companies} companies · replay mode` : "connecting…"}</span>
      </header>
      <main className="max-w-5xl w-full mx-auto px-4 py-6 flex-1">
        <AnimatePresence mode="wait">
          <motion.div key={route.name} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}>
            {route.name === "home" && <Select />}
            {route.name === "run" && <Run id={route.id} />}
            {route.name === "verdict" && <Verdict id={route.id} />}
            {route.name === "mubit" && <Mubit agent={route.agent} />}
          </motion.div>
        </AnimatePresence>
      </main>
      <footer className="text-center text-xs mute py-6 px-4">Research tool, not financial advice. Assessments describe business evidence in filings, not investment advice or a recommendation to trade.</footer>
    </div>
  );
}
