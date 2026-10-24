import { useEffect, useState, type MouseEvent } from "react";

/** Hash routes so every page is linkable: #/, #/assess/<company>/<asOf>[/run], #/mubit[/<agent>]. */
/** One company, three separate pages: the written report, the animated investors (with chat), and the professional tables. */
export type ResearchView = "report" | "investors" | "pro";

export type Route =
  | { name: "home" }
  | { name: "research"; cik: string; view: ResearchView }
  | { name: "run"; id: string }
  | { name: "verdict"; id: string }
  | { name: "mubit"; agent?: string };

export function parseHash(hash: string): Route {
  const p = hash.replace(/^#\/?/, "").split("?")[0].split("/").filter(Boolean).map(decodeURIComponent);
  if (p[0] === "assess" && p[1] && p[2]) {
    const id = `${p[1]}_${p[2]}`;
    return p[3] === "run" ? { name: "run", id } : { name: "verdict", id };
  }
  if (p[0] === "research" && /^\d+$/.test(p[1] ?? "")) return { name: "research", cik: p[1], view: p[2] === "investors" ? "investors" : p[2] === "pro" ? "pro" : "report" };
  if (p[0] === "mubit") return { name: "mubit", agent: p[1] };
  return { name: "home" };
}

/** assessment id is "<company>_<asOf>" (see api/service.py). */
export function assessHref(id: string, run = false) {
  const i = id.lastIndexOf("_");
  return `#/assess/${encodeURIComponent(id.slice(0, i))}/${encodeURIComponent(id.slice(i + 1))}${run ? "/run" : ""}`;
}
export const mubitHref = (agent?: string) => (agent ? `#/mubit/${encodeURIComponent(agent)}` : "#/mubit");
export const researchHref = (cik: number | string, view: ResearchView = "report") => (view === "report" ? `#/research/${cik}` : `#/research/${cik}/${view}`);
export const go = (href: string) => { window.location.hash = href; };

/** Presenter mode: `?demo=1` before the # (http://localhost:5173/?demo=1#/research/320193) or after the route (#/research/320193?demo=1). */
export function demoMode(): boolean {
  const flag = (q: string) => new URLSearchParams(q).get("demo") === "1";
  return flag(window.location.search) || flag(window.location.hash.split("?")[1] ?? "");
}

/** onClick for an in-page link (href="#some-id"): scroll to the element and leave the route alone. */
export const jumpTo = (id: string) => (e: MouseEvent) => {
  e.preventDefault();
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
};

export function useRoute(): Route {
  const [r, setR] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const f = () => {
      const h = window.location.hash;
      if (h && !h.startsWith("#/")) return;     // an in-page link such as #lens-buffett is not a page change
      setR(parseHash(h)); window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return r;
}

export function useReducedMotion() {
  const q = "(prefers-reduced-motion: reduce)";
  const [v, setV] = useState(() => window.matchMedia(q).matches);
  useEffect(() => {
    const m = window.matchMedia(q);
    const f = () => setV(m.matches);
    m.addEventListener("change", f);
    return () => m.removeEventListener("change", f);
  }, []);
  return v;
}
