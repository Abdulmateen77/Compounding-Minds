import { STANCE_COLOR } from "../api/client";
import type { ChatMsg } from "../chat";
import { stanceOf, surname } from "../scene/lenses";
import InvestorPanel from "../scene/InvestorPanel";
import { CALL_COLOR, type Lens } from "../research";
import { Avatar } from "./Avatar";
import { Head } from "./Section";

/** The ask box: choose an investor, then question them one-on-one. They answer only from their own checks on this company. It is
    open from the first moment; nothing has to be watched or played first. */
export function AskInvestor({ cik, lenses, sel, setSel, chats, setChats, focus }: {
  cik: number; lenses: Lens[]; sel: number | null; setSel: (i: number | null) => void;
  chats: Record<string, ChatMsg[]>; setChats: (f: (c: Record<string, ChatMsg[]>) => Record<string, ChatMsg[]>) => void;
  focus: boolean;      // the reader chose someone: put the cursor in the box
}) {
  const lens = sel != null ? lenses[sel] : null;
  return (
    <section id="ask" className="grid gap-3 grid-cols-[minmax(0,1fr)]" aria-label="Ask an investor" style={{ scrollMarginTop: 72 }}>
      <Head title="Ask an investor" blurb="Question any of them about their call. They answer from their own checks on this company, and say so when something is not in them." />
      <div role="group" aria-label="Who to ask" className="flex flex-wrap gap-2">
        {lenses.map((l, i) => {
          const c = l.decision ? CALL_COLOR[l.decision.call] : STANCE_COLOR[stanceOf(l.fit)], on = sel === i;
          return (
            <button key={l.key} aria-pressed={on} onClick={() => setSel(on ? null : i)}
              className="card flex items-center gap-2 pl-2 pr-3 cursor-pointer" style={{ minHeight: 48, color: "var(--foreground)", borderColor: on ? c : undefined, boxShadow: on ? `0 0 0 2px ${c}` : undefined }}>
              <Avatar l={l} size={32} ring={on ? c : undefined} />
              <span className="text-sm font-medium">{surname(l)}</span>
            </button>
          );
        })}
      </div>
      {lens
        ? <InvestorPanel key={lens.key} inline autoFocus={focus} cik={cik} lens={lens} onClose={() => setSel(null)}
            messages={chats[lens.key] ?? []} setMessages={(f) => setChats((c) => ({ ...c, [lens.key]: f(c[lens.key] ?? []) }))} />
        : <p className="card p-4 m-0 text-sm mute">Choose an investor above to start.</p>}
    </section>
  );
}
