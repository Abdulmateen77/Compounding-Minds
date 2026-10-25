import { useCallback, useRef, useState } from "react";
import type { Report } from "../research";
import { demoMode } from "../route";
import { DebateLog, type Speech } from "./DebateLog";
import { InvestorStage } from "./InvestorStage";
import { Head } from "./Section";

/** Where the investors disagree. The written debate is always here; the 3D version opens on request, so nobody downloads or waits
    for it who only wants the answer. While the written debate runs, whoever is speaking has their line said in the 3D view too. */
export function DebateSection({ r, fromLoading, onPick }: { r: Report; fromLoading: boolean; onPick: (i: number) => void }) {
  const [watching, setWatching] = useState(demoMode);          // a presenter link (?demo=1) opens the 3D view straight away
  const [speech, setSpeech] = useState<Speech | null>(null);
  const box = useRef<HTMLDivElement | null>(null), speaking = useRef(false);
  const a = r.analysis!;

  const onSpeak = useCallback((s: Speech | null) => {
    if (s && !speaking.current) box.current?.scrollIntoView({ behavior: "smooth", block: "start" });   // bring the 3D view into sight as it starts
    speaking.current = !!s;
    setSpeech(s);
  }, []);

  return (
    <section className="grid gap-3 grid-cols-[minmax(0,1fr)]" aria-label="The debate">
      <Head title="The debate" blurb="Where the investors disagree, line by line, taken from their own checks. Read it, or watch it played out in a 3D office."
        right={<button className="btn ghost" aria-expanded={watching} onClick={() => setWatching((w) => !w)}>{watching ? "Hide the 3D view" : "Watch it in 3D"}</button>} />
      {watching && <div ref={box} style={{ scrollMarginTop: 72 }}><InvestorStage r={r} fromLoading={fromLoading} speech={speech} onPick={onPick} /></div>}
      <DebateLog a={a} company={r.company.name} onSpeak={onSpeak} heading={false} />
    </section>
  );
}
