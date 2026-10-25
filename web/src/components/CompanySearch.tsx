import { useEffect, useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { SPEEDS, setPrefs, usePrefs } from "../prefs";
import { rememberPicked } from "../recent";
import type { Candidate, SearchResult } from "../research";
import { go, researchHref, type ResearchView } from "../route";

const getJson = async <T,>(url: string): Promise<T> => {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText);
  return r.json();
};

/** Company search that works from the keyboard (arrows, Enter, Escape) and opens the company on the page the reader chose in
    the search options. `compact` is the small version in the page header; the hero version lives on the landing page. */
export function CompanySearch({ q, onQ, compact = false, autoFocus = false }: { q?: string; onQ?: (v: string) => void; compact?: boolean; autoFocus?: boolean }) {
  const [own, setOwn] = useState("");
  const value = q ?? own, set = onQ ?? setOwn;
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(true);
  const [active, setActive] = useState(0);
  const prefs = usePrefs();
  const box = useRef<HTMLDivElement>(null);
  const list = useId();

  useEffect(() => { const t = setTimeout(() => setDebounced(value.trim()), 220); return () => clearTimeout(t); }, [value]);
  useEffect(() => { setActive(0); setOpen(true); }, [debounced]);
  const s = useQuery({ queryKey: ["rsearch", debounced], enabled: debounced.length >= 2, queryFn: () => getJson<SearchResult>(`/api/research/search?q=${encodeURIComponent(debounced)}`) });
  const results = s.data?.results ?? [];
  const showing = open && debounced.length >= 2;

  const pick = (c: Candidate) => { rememberPicked({ cik: c.cik, name: c.name, ticker: c.ticker }); set(""); setOpen(false); go(researchHref(c.cik, prefs.open)); };
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" && results.length) { e.preventDefault(); setOpen(true); setActive((a) => (a + 1) % results.length); }
    else if (e.key === "ArrowUp" && results.length) { e.preventDefault(); setActive((a) => (a - 1 + results.length) % results.length); }
    else if (e.key === "Enter" && showing && results[active]) { e.preventDefault(); pick(results[active]); }
    else if (e.key === "Escape") setOpen(false);
  };

  return (
    <div ref={box} className={compact ? "relative w-full sm:w-72" : "max-w-2xl relative"}
      onBlur={(e) => { if (!box.current?.contains(e.relatedTarget as Node | null)) setOpen(false); }}>
      <input autoFocus={autoFocus} value={value} onChange={(e) => set(e.target.value)} onKeyDown={onKeyDown} onFocus={() => setOpen(true)}
        role="combobox" aria-expanded={showing} aria-controls={list} aria-autocomplete="list" aria-label="Search a company by name or ticker"
        aria-activedescendant={showing && results[active] ? `${list}-${active}` : undefined} autoComplete="off" spellCheck={false}
        placeholder={compact ? "Search a company or ticker" : "Company name or ticker, for example Tesla or TSLA"}
        className={`card w-full outline-none ${compact ? "px-3 py-2 text-sm" : "px-5 py-4 text-lg"}`} style={{ color: "var(--text)", borderColor: compact ? undefined : "var(--blue)" }} />
      {showing && (
        <div id={list} role="listbox" aria-label="Matching companies" className={`card absolute mt-2 z-30 overflow-hidden ${compact ? "right-0 w-[min(92vw,22rem)]" : "left-0 right-0"}`} style={{ boxShadow: "0 12px 40px rgba(0,0,0,.25)" }}>
          {s.isLoading && <div className="p-4 mute text-sm" role="status">Searching the SEC company list…</div>}
          {s.isError && <div className="p-4 text-sm" role="alert" style={{ color: "var(--red)" }}>Could not reach the search. Is the API running?</div>}
          {results.map((c, i) => (
            <div key={c.cik} id={`${list}-${i}`} role="option" aria-selected={i === active} tabIndex={-1}
              onMouseDown={(e) => e.preventDefault()} onClick={() => pick(c)} onMouseEnter={() => setActive(i)}
              className="w-full text-left px-4 py-3 flex items-center justify-between gap-3 cursor-pointer"
              style={{ color: "var(--text)", borderBottom: "1px solid var(--line)", background: i === active ? "var(--panel2)" : "transparent" }}>
              <span><span className="font-semibold">{c.name}</span> <span className="num mute text-sm">{c.ticker}</span></span>
              {!compact && <span className="chip">{c.exchange ?? "US"} · United States</span>}
            </div>
          ))}
          {s.data && results.length === 0 && <div className="p-4 text-sm">{s.data.message}</div>}
        </div>
      )}
    </div>
  );
}

const OPEN: { id: ResearchView; label: string; hint: string }[] = [
  { id: "overview", label: "Overview", hint: "The short answer first, in plain English" },
  { id: "investors", label: "Investor panel", hint: "The investors debate it face to face, and you can question each one" },
];

const chipStyle = (on: boolean) => (on ? { color: "var(--text)", borderColor: "var(--blue)", background: "color-mix(in srgb, var(--blue) 14%, transparent)" } : undefined);

/** What to open and how fast the investor panel plays, chosen at search time and remembered in this browser. */
export function SearchOptions() {
  const p = usePrefs();
  return (
    <div className="flex flex-wrap gap-x-8 gap-y-3 items-center text-sm" aria-label="Search options">
      <div role="group" aria-label="Open the company as" className="flex items-center gap-2 flex-wrap">
        <span className="mute text-xs">Open as</span>
        {OPEN.map((o) => (
          <button key={o.id} type="button" className="chip cursor-pointer" style={{ minHeight: 34, ...chipStyle(p.open === o.id) }} title={o.hint}
            aria-pressed={p.open === o.id} onClick={() => setPrefs({ open: o.id })}>{p.open === o.id ? "✓ " : ""}{o.label}</button>
        ))}
      </div>
      <div role="group" aria-label="Investor panel speed" className="flex items-center gap-2">
        <span className="mute text-xs">Panel speed</span>
        {SPEEDS.map((s) => (
          <button key={s} type="button" className="chip cursor-pointer num" style={{ minHeight: 34, ...chipStyle(p.speed === s) }}
            aria-pressed={p.speed === s} onClick={() => setPrefs({ speed: s })}>{s}x</button>
        ))}
      </div>
    </div>
  );
}
