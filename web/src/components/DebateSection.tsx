import type { Report } from "../research";
import { DebateLog, type Speech } from "./DebateLog";
import { Head } from "./Section";

/** Where the investors disagree, written out line by line from their own checks. The 3D office at the top of the tab plays the same
    debate; whoever is speaking here has their line said over their head there too (`onSpeak`). */
export function DebateSection({ r, onSpeak }: { r: Report; onSpeak: (s: Speech | null) => void }) {
  return (
    <section className="grid gap-3 grid-cols-[minmax(0,1fr)]" aria-label="The debate">
      <Head title="The debate, in writing" blurb="Where the investors disagree, line by line, taken from their own checks. Press play to watch it in the office above." />
      <DebateLog a={r.analysis!} company={r.company.name} onSpeak={onSpeak} heading={false} />
    </section>
  );
}
