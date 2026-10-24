/** Client for the one-on-one chat with an investor lens (research/chat.py answers it from that lens's checks). */
export type ChatMsg = { role: "user" | "assistant"; content: string; source?: "model" | "rules" };

export async function askInvestor(cik: number | string, lens: string, question: string, history: ChatMsg[]): Promise<{ answer: string; source: "model" | "rules" }> {
  const r = await fetch(`/api/research/company/${cik}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lens, question, history: history.slice(-12).map(({ role, content }) => ({ role, content })) }),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText);
  return r.json();
}
