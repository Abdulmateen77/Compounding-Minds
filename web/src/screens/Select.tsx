import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { ErrorBox, Skeleton } from "../components/bits";
import { ShowcaseHero } from "../components/Showcase";
import { assessHref, go } from "../route";

export default function Select() {
  const companies = useQuery({ queryKey: ["companies"], queryFn: api.companies });
  const [q, setQ] = useState("");
  const [sector, setSector] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [asOf, setAsOf] = useState<string>("");
  const quarters = useQuery({ queryKey: ["quarters", sel], queryFn: () => api.quarters(sel!), enabled: !!sel });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const list = (companies.data ?? []).filter((c) => (!sector || c.sector === sector) && `${c.name} ${c.id} ${c.sector ?? ""}`.toLowerCase().includes(q.toLowerCase()));
  const sectors = [...new Set((companies.data ?? []).map((c) => c.sector).filter(Boolean))] as string[];
  const chosen = asOf || quarters.data?.[quarters.data.length - 1] || "";

  async function convene() {
    if (!sel) return;
    setBusy(true); setErr(null);
    try { go(assessHref((await api.start(sel, chosen || undefined)).assessment_id, true)); }
    catch (e) { setErr(String(e)); setBusy(false); }
  }

  return (
    <div>
      <ShowcaseHero />
      <h2 className="text-xl font-semibold tracking-tight m-0">Pick a company</h2>

      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search companies…" aria-label="Search companies"
        className="card w-full mt-4 px-4 py-3 outline-none" style={{ color: "var(--text)" }} />

      {sectors.length > 1 && (
        <div className="flex flex-wrap gap-2 mt-3" role="group" aria-label="Sector filter">
          {[null, ...sectors].map((s) => (
            <button key={s ?? "all"} onClick={() => setSector(s)} aria-pressed={sector === s} className="chip cursor-pointer bg-transparent"
              style={sector === s ? { color: "var(--text)", borderColor: "var(--blue)" } : undefined}>{s ?? "All sectors"}</button>
          ))}
        </div>
      )}
      {companies.isError && <div className="mt-4"><ErrorBox msg="Could not reach the API. Is it running?" onRetry={() => companies.refetch()} /></div>}
      {companies.isLoading && <div className="grid gap-3 mt-4 sm:grid-cols-2 lg:grid-cols-3"><Skeleton h={110} /><Skeleton h={110} /><Skeleton h={110} /></div>}
      {companies.data && list.length === 0 && <p className="mute mt-4">{companies.data.length === 0 ? "No stored runs found. Generate a replay first (see README)." : "No companies match."}</p>}
      <div className="grid gap-3 mt-4 sm:grid-cols-2 lg:grid-cols-3">
        {list.map((c) => (
          <button key={c.id} onClick={() => { setSel(c.id); setAsOf(""); }} aria-pressed={sel === c.id}
            className="card text-left p-4 cursor-pointer transition-transform hover:-translate-y-0.5"
            style={{ color: "var(--text)", borderColor: sel === c.id ? "var(--blue)" : undefined, boxShadow: sel === c.id ? "0 0 0 2px color-mix(in srgb,var(--blue) 35%,transparent)" : undefined }}>
            <div className="font-semibold">{c.name}</div>
            <div className="mute text-sm mt-1">{c.sector ?? "Sector n/a"}</div>
            <div className="flex gap-2 mt-3"><span className="chip num">{c.id}</span>{c.held_out && <span className="chip">held out</span>}</div>
          </button>
        ))}
      </div>

      <div className="card mt-6 p-4 flex flex-wrap items-center gap-3 sticky bottom-4" style={{ backdropFilter: "blur(10px)" }}>
        <span className="mute text-sm">{sel ? `Selected: ${companies.data?.find((c) => c.id === sel)?.name}` : "Select a company"}</span>
        <label className="ml-auto text-sm mute flex items-center gap-2">As of
          <select value={chosen} onChange={(e) => setAsOf(e.target.value)} disabled={!sel} className="card px-3 py-2 num" style={{ color: "var(--text)" }}>
            {(quarters.data ?? []).map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
        <button className="btn" disabled={!sel || busy || !chosen} onClick={convene}>{busy ? "Starting…" : "Convene committee"}</button>
      </div>
      {err && <div className="mt-3"><ErrorBox msg={err} /></div>}
    </div>
  );
}
