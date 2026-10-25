import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "./api/client";
import { useRoute } from "./route";
import Run from "./screens/Run";
import Verdict from "./screens/Verdict";
import Mubit from "./screens/Mubit";
import Research from "./screens/Research";
import { CompanySearch } from "./components/CompanySearch";
import { DUR, EASE_SOFT } from "./motion";

export default function App() {
  const route = useRoute();
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const onMubit = route.name === "mubit";
  const onResearch = route.name === "home" || route.name === "research";

  return (
    <div className="min-h-screen flex flex-col">
      <a href="#main" className="skip" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }}>Skip to the content</a>
      {health.data?.banner && (
        <div role="status" className="text-center text-xs py-2 px-4" style={{ background: "color-mix(in srgb, var(--warning) 16%, transparent)", color: "var(--warning)", borderBottom: "1px solid var(--divider)" }}>
          {health.data.banner}
        </div>
      )}
      <header className="topbar sticky top-0 z-[var(--z-sticky)]">
        <div className="page h-12 flex items-center gap-x-4">
          <a href="#/" className="flex items-center gap-2 text-sm font-semibold no-underline shrink-0" style={{ color: "var(--foreground)" }}>
            <span className="inline-block w-5 h-5 rounded-lg" style={{ background: "var(--primary-solid)" }} aria-hidden />
            <span className="hidden xs:inline">Compounding Minds</span>
          </a>
          <div className="flex-1 min-w-0 flex justify-center sm:justify-start">{route.name !== "home" && <CompanySearch compact />}</div>
          <nav aria-label="Pages" className="flex gap-4 text-sm font-medium h-full shrink-0">
            <a href="#/" aria-current={onResearch ? "page" : undefined} className="navlink inline-flex items-center no-underline">Research</a>
            <a href="#/mubit" aria-current={onMubit ? "page" : undefined} className="navlink inline-flex items-center no-underline">Track record</a>
          </nav>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="page py-4 flex-1 outline-none">
        <AnimatePresence mode="wait">
          <motion.div key={route.name} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0, transition: { duration: DUR.slow, ease: EASE_SOFT } }} exit={{ opacity: 0, transition: { duration: DUR.fast } }}>
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
