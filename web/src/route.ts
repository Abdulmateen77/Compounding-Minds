import { useEffect, useState } from "react";

/** Hash routes so every page is linkable: #/, #/assess/<company>/<asOf>[/run], #/mubit[/<agent>]. */
export type Route =
  | { name: "home" }
  | { name: "past" }
  | { name: "research"; cik: string }
  | { name: "run"; id: string }
  | { name: "verdict"; id: string }
  | { name: "mubit"; agent?: string };

export function parseHash(hash: string): Route {
  const p = hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (p[0] === "assess" && p[1] && p[2]) {
    const id = `${p[1]}_${p[2]}`;
    return p[3] === "run" ? { name: "run", id } : { name: "verdict", id };
  }
  if (p[0] === "research" && /^\d+$/.test(p[1] ?? "")) return { name: "research", cik: p[1] };
  if (p[0] === "past") return { name: "past" };
  if (p[0] === "mubit") return { name: "mubit", agent: p[1] };
  return { name: "home" };
}

/** assessment id is "<company>_<asOf>" (see api/service.py). */
export function assessHref(id: string, run = false) {
  const i = id.lastIndexOf("_");
  return `#/assess/${encodeURIComponent(id.slice(0, i))}/${encodeURIComponent(id.slice(i + 1))}${run ? "/run" : ""}`;
}
export const mubitHref = (agent?: string) => (agent ? `#/mubit/${encodeURIComponent(agent)}` : "#/mubit");
export const researchHref = (cik: number | string) => `#/research/${cik}`;
export const go = (href: string) => { window.location.hash = href; };

export function useRoute(): Route {
  const [r, setR] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const f = () => { setR(parseHash(window.location.hash)); window.scrollTo(0, 0); };
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
