import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "./api/client";
import { useRoute } from "./route";
import Run from "./screens/Run";
import Verdict from "./screens/Verdict";
import Mubit from "./screens/Mubit";
import Research from "./screens/Research";
import { CompanySearch } from "./components/CompanySearch";
import { DUR } from "./motion";

export default function App() {
  const route = useRoute();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const onMubit = route.name === "mubit";
  const onResearch = route.name === "home" || route.name === "research";
  const navStyle = (on: boolean) => ({ color: on ? "var(--foreground)" : "var(--muted)", borderBottom: `2px solid ${on ? "var(--primary)" : "transparent"}` });

  return (
    <div className="min-h-screen flex flex-col">
      <a href="#main" className="skip" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>Skip to the content</a>
      {health.data?.banner && (
        <div role="status" className="text-center text-xs py-2 px-4" style={{ background: "color-mix(in srgb, var(--warning) 16%, transparent)", color: "var(--warning)", borderBottom: "1px solid var(--divider)" }}>
          {health.data.banner}
        </div>
      )}
      <header className="page pt-6 pb-2 flex items-center justify-between gap-x-4 gap-y-2 flex-wrap">
        <a href="#/" className="flex items-center gap-2 py-2 font-semibold tracking-tight no-underline" style={{ color: "var(--foreground)" }}>
          <span className="inline-block w-6 h-6 rounded-lg" style={{ background: "linear-gradient(135deg,var(--primary),var(--secondary))" }} aria-hidden />
          Compounding Minds
        </a>
        <nav aria-label="Pages" className="flex gap-5 text-sm font-medium">
          <a href="#/" aria-current={onResearch ? "page" : undefined} className="py-1 no-underline" style={navStyle(onResearch)}>Research</a>
          <a href="#/mubit" aria-current={onMubit ? "page" : undefined} className="py-1 no-underline" style={navStyle(onMubit)}>Track record</a>
        </nav>
        {route.name !== "home" && <CompanySearch compact />}
      </header>
      <main id="main" tabIndex={-1} className="page py-6 flex-1 outline-none">
        <AnimatePresence mode="wait">
          <motion.div key={route.name} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: DUR.base }}>
            {route.name === "home" && <Research />}
            {route.name === "research" && <Research cik={route.cik} view={route.view} />}
            {route.name === "run" && <Run id={route.id} />}
            {route.name === "verdict" && <Verdict id={route.id} />}
            {route.name === "mubit" && <Mubit agent={route.agent} />}
          </motion.div>
        </AnimatePresence>
      </main>
      <footer className="text-center text-xs mute py-6 px-4" style={{ paddingBottom: "max(1.5rem, env(safe-area-inset-bottom))" }}>Research tool, not financial advice. Assessments describe business evidence in filings, not investment advice or a recommendation to trade.</footer>
    </div>
  );
}
