import type { components } from "./schema";

export type Assessment = components["schemas"]["Assessment"];
export type AgentView = components["schemas"]["AgentView"];
export type Company = components["schemas"]["Company"];
export type Health = components["schemas"]["Health"];
export type MubitState = components["schemas"]["MubitState"];
export type Correction = components["schemas"]["Correction"];
export type TrackRecord = components["schemas"]["TrackRecord"];

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  health: () => j<Health>("/api/health"),
  companies: () => j<Company[]>("/api/companies"),
  quarters: (id: string) => j<string[]>(`/api/companies/${id}/quarters`),
  start: (company_id: string, as_of?: string) =>
    j<{ assessment_id: string }>("/api/assessments", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ company_id, as_of }),
    }),
  assessment: (id: string) => j<Assessment>(`/api/assessments/${id}`),
  trackRecord: (agent: string, asOf?: string) => j<TrackRecord>(`/api/agents/${agent}/track-record${asOf ? `?as_of=${asOf}` : ""}`),
};

export const LABELS = {
  investable: { text: "Investable on evidence", color: "var(--green)" },
  watch: { text: "Watch", color: "var(--amber)" },
  not_investable: { text: "Not investable on evidence", color: "var(--red)" },
} as const;

export const STANCE_COLOR = { for: "var(--green)", neutral: "var(--amber)", against: "var(--red)" } as const;
export const pct = (x: number) => `${Math.round(x * 100)}%`;
