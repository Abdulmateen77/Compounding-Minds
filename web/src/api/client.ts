import type { components } from "./schema";

export type Assessment = components["schemas"]["Assessment"];
export type AgentView = components["schemas"]["AgentView"];
export type Company = components["schemas"]["Company"];
export type Health = components["schemas"]["Health"];
export type MubitState = components["schemas"]["MubitState"];
export type Correction = components["schemas"]["Correction"];
export type TrackRecord = components["schemas"]["TrackRecord"];

/** eval/report.py's held-out report, as /api/heldout serves it (not in the OpenAPI schema: it is passed through as written). */
export type Score = { n: number; accuracy: number | null; brier: number | null };
export type HeldOutSegment = Score & {
  frozen: Score; learned: Score; baselines: Record<string, Score>;
  learned_minus_frozen: { accuracy: number | null; brier: number | null };
};
export type HeldOutAgent = { corrections_applied: number; learned_version_end: string | null; segments: Record<string, HeldOutSegment> };
export type HeldOutReport = {
  banner: string | null; generated_at: string;
  split: { train_window: [string, string]; held_out_window: [string, string]; train_companies: string[]; held_out_companies: string[] };
  agents: Record<string, HeldOutAgent>;
};

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
  heldout: () => j<{ path: string; report: HeldOutReport }>("/api/heldout"),
};

export const LABELS = {
  investable: { text: "Investable on evidence", color: "var(--success)" },
  watch: { text: "Watch", color: "var(--warning)" },
  not_investable: { text: "Not investable on evidence", color: "var(--error)" },
} as const;

export const STANCE_COLOR = { for: "var(--success)", neutral: "var(--warning)", against: "var(--error)" } as const;
export const pct = (x: number) => `${Math.round(x * 100)}%`;
