import { useEffect, useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarsLoader } from "./bits";
import { SPEEDS, setPrefs, usePrefs } from "../prefs";
import { recallRecent, rememberPicked, type Picked } from "../recent";
import type { SearchResult } from "../research";
import { go, researchHref, type ResearchView } from "../route";

const getJson = async <T,>(url: string): Promise<T> => {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText);
  return r.json();
};

type Row = Picked & { exchange?: string | null };

const OPEN: { id: ResearchView; label: string; hint: string }[] = [
  { id: "overview", label: "Overview", hint: "The short answer first, in plain English" },
  { id: "investors", label: "Investor panel", hint: "The investors debate it face to face, and you can question each one" },
];
const labelOf = (v: ResearchView) => OPEN.find((o) => o.id === v)?.label ?? "Overview";
const otherOf = (v: ResearchView): ResearchView => (v === "investors" ? "overview" : "investors");

const chipStyle = (on: boolean) => (on ? { color: "var(--foreground)", borderColor: "var(--primary)", background: "color-mix(in srgb, var(--primary) 14%, transparent)" } : undefined);

/** The name with the part the reader typed in bold, so it is clear why a row matched. */
function Marked({ text, q }: { text: string; q: string }) {
  const i = q ? text.toLowerCase().indexOf(q.toLowerCase()) : -1;
  if (i < 0) return <span className="font-semibold">{text}</span>;
  return <span><span className="font-semibold">{text.slice(0, i)}</span><mark className="font-bold bg-transparent" style={{ color: "var(--primary)" }}>{text.slice(i, i + q.length)}</mark><span className="font-semibold">{text.slice(i + q.length)}</span></span>;
}

/** What to open and how fast the investor panel plays. It sits inside the results, so it is in front of the reader at the moment
    they pick a company, and it is remembered in this browser. */
function PickOptions() {
  const p = usePrefs();
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-2 items-center text-sm px-3 py-2" style={{ borderBottom: "1px solid var(--divider)", background: "var(--card-alt)" }} aria-label="How to open the company">
      <div role="group" aria-label="Open the company as" className="flex items-center gap-1.5 flex-wrap">
        <span className="mute text-xs">Open as</span>
        {OPEN.map((o) => (
          <button key={o.id} type="button" className="chip cursor-pointer" style={chipStyle(p.open === o.id)} title={o.hint}
            aria-pressed={p.open === o.id} onClick={() => setPrefs({ open: o.id })}>{o.label}</button>
        ))}
      </div>
      {p.open === "investors" && (
        <div role="group" aria-label="Investor panel speed" className="flex items-center gap-1.5">
          <span className="mute text-xs">Speed</span>
          {SPEEDS.map((s) => (
            <button key={s} type="button" className="chip cursor-pointer num" style={chipStyle(p.speed === s)}
              aria-pressed={p.speed === s} onClick={() => setPrefs({ speed: s })}>{s}x</button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Company search that works from the keyboard (arrows, Enter, Escape). The results show how the company will open and let the
    reader change that on the spot; focusing an empty box lists the companies searched for recently. `compact` is the small
    version in the page header; the hero version lives on the landing page. */
export function CompanySearch({ q, onQ, compact = false, autoFocus = false }: { q?: string; onQ?: (v: string) => void; compact?: boolean; autoFocus?: boolean }) {
  const [own, setOwn] = useState("");
  const value = q ?? own, set = onQ ?? setOwn;
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);              // opens when the box is focused, never on its own
  const [active, setActive] = useState(0);
  const [recent, setRecent] = useState<Picked[]>([]);
  const prefs = usePrefs();
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const list = useId();

  const term = value.trim();
  const typing = term.length >= 1;
  useEffect(() => { const t = setTimeout(() => setDebounced(term), 200); return () => clearTimeout(t); }, [term]);
  useEffect(() => { setActive(0); if (document.activeElement === input.current) setOpen(true); }, [debounced]);
  const s = useQuery({ queryKey: ["rsearch", debounced], enabled: debounced.length >= 1, queryFn: () => getJson<SearchResult>(`/api/research/search?q=${encodeURIComponent(debounced)}`) });

  const searching = typing && debounced === term;       // results on screen belong to what is in the box
  const rows: Row[] = typing ? (s.data?.results ?? []) : recent;
  const showing = open && (typing || recent.length > 0);

  const refreshRecent = () => setRecent(recallRecent());
  useEffect(refreshRecent, []);

  const pick = (c: Row, view: ResearchView = prefs.open) => {
    rememberPicked({ cik: c.cik, name: c.name, ticker: c.ticker });
    refreshRecent(); set(""); setOpen(false); input.current?.blur();
    go(researchHref(c.cik, view));
  };
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" && rows.length) { e.preventDefault(); setOpen(true); setActive((a) => (a + 1) % rows.length); }
    else if (e.key === "ArrowUp" && rows.length) { e.preventDefault(); setActive((a) => (a - 1 + rows.length) % rows.length); }
    else if (e.key === "Enter" && showing && rows[active]) { e.preventDefault(); pick(rows[active], e.shiftKey ? otherOf(prefs.open) : prefs.open); }
    else if (e.key === "Escape") { if (open) setOpen(false); else if (value) set(""); }
  };

  return (
    <div ref={box} className={compact ? "relative w-full max-w-sm" : "max-w-2xl relative"}
      onBlur={(e) => { if (!box.current?.contains(e.relatedTarget as Node | null)) setOpen(false); }}>
      {compact && <svg aria-hidden viewBox="0 0 20 20" width="14" height="14" className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" fill="none" stroke="var(--muted)" strokeWidth="1.8" strokeLinecap="round"><circle cx="8.5" cy="8.5" r="5.5" /><path d="M13 13l4 4" /></svg>}
      <input ref={input} maxLength={80} autoFocus={autoFocus && !window.matchMedia("(pointer: coarse)").matches} value={value} onChange={(e) => set(e.target.value)} onKeyDown={onKeyDown} onFocus={() => { refreshRecent(); setOpen(true); }} onClick={() => setOpen(true)}
        role="combobox" aria-expanded={showing} aria-controls={list} aria-autocomplete="list" aria-label="Search a company by name or ticker"
        aria-activedescendant={showing && rows[active] ? `${list}-${active}` : undefined} autoComplete="off" spellCheck={false} enterKeyHint="go"
        placeholder={compact ? "Search a company or ticker" : "Company name or ticker, for example Tesla or TSLA"}
        className={`field w-full outline-none ${compact ? "pl-9 pr-8 min-h-8 text-sm" : "px-4 pr-11 min-h-12 text-lg"}`} style={compact ? undefined : { borderColor: "var(--divider)" }} />
      {value && (
        <button type="button" aria-label="Clear the search" onMouseDown={(e) => e.preventDefault()} onClick={() => { set(""); input.current?.focus(); }}
          className={`absolute top-1/2 -translate-y-1/2 grid place-items-center rounded-full cursor-pointer bg-transparent border-0 ${compact ? "right-1.5 w-6 h-6" : "right-3 w-8 h-8"}`} style={{ color: "var(--muted)" }}>
          <svg aria-hidden viewBox="0 0 20 20" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M5 5l10 10M15 5L5 15" /></svg>
        </button>
      )}
      {showing && (
        <div className={`card absolute mt-1 z-[var(--z-popover)] overflow-hidden ${compact ? "left-0 w-[min(92vw,26rem)]" : "left-0 right-0"}`} style={{ boxShadow: "var(--shadow-lg)" }} onMouseDown={(e) => e.preventDefault()}>
          <PickOptions />
          {!typing && <div className="px-3 pt-2 pb-1 mute text-xs">Recent</div>}
          <div id={list} role="listbox" aria-label={typing ? "Matching companies" : "Recent companies"}>
            {typing && s.isFetching && rows.length === 0 && <div className="p-4 mute text-sm flex items-center gap-3" role="status"><BarsLoader />Searching the SEC company list…</div>}
            {typing && s.isError && <div className="p-4 text-sm" role="alert" style={{ color: "var(--error)" }}>Could not reach the search. Is the API running?</div>}
            {rows.map((c, i) => (
              <div key={c.cik} className="flex items-stretch" style={{ borderBottom: "1px solid var(--divider)", background: i === active ? "var(--card-alt)" : "transparent" }} onMouseEnter={() => setActive(i)}>
                <div id={`${list}-${i}`} role="option" aria-selected={i === active} tabIndex={-1} onClick={() => pick(c)}
                  className="flex-1 min-w-0 text-left px-3 py-2 text-sm flex items-center gap-x-3 gap-y-0.5 flex-wrap cursor-pointer min-h-11" style={{ color: "var(--foreground)" }}>
                  {typing ? <Marked text={c.name} q={term} /> : <span className="font-semibold">{c.name}</span>}
                  {c.ticker && <span className="num mute text-sm">{c.ticker}</span>}
                  {!compact && typing && "exchange" in c && <span className="chip hidden sm:inline-flex">{c.exchange ?? "US"} · United States</span>}
                </div>
                <button type="button" tabIndex={-1} onClick={() => pick(c, otherOf(prefs.open))} title={`Open ${c.name} as ${labelOf(otherOf(prefs.open))} instead`}
                  aria-label={`Open ${c.name} as ${labelOf(otherOf(prefs.open))} instead`}
                  className="px-3 text-xs cursor-pointer bg-transparent border-0 whitespace-nowrap" style={{ color: i === active ? "var(--primary)" : "var(--muted)" }}>
                  {otherOf(prefs.open) === "investors" ? "Panel" : "Overview"} →
                </button>
              </div>
            ))}
            {searching && s.data && rows.length === 0 && <div className="p-4 text-sm">{s.data.message}</div>}
          </div>
          {rows.length > 0 && (
            <div className="hidden sm:flex px-3 py-1.5 text-xs mute gap-x-4 flex-wrap" aria-hidden>
              <span>↑↓ to move</span><span>Enter opens as {labelOf(prefs.open)}</span><span>Shift+Enter opens as {labelOf(otherOf(prefs.open))}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
