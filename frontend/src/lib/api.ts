// Typed API client. All requests are same-origin with the session cookie; mutating requests carry
// the X-Requested-With header the backend requires (CSRF defence in addition to SameSite cookies).

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "X-Requested-With": "shadowtrace", Accept: "application/json" };
  if (init.body) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { credentials: "same-origin", ...init, headers: { ...headers, ...(init.headers as object) } });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const detail = data?.detail;
    const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d: { msg: string }) => d.msg).join("; ") : res.statusText;
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

// ── Types ─────────────────────────────────────────────
export interface CountryRef { code: string; name: string }
export interface GroupRef { id: number; slug: string; name: string; kind: string; origin_country: CountryRef | null }
export interface StateLink {
  country: CountryRef; relation: string; agency: string | null; confidence: string; origin: string;
  note: string | null; source_name: string | null; source_url: string | null;
}
export interface GroupListItem extends GroupRef {
  attack_id: string | null; aliases: string[]; motivation: string | null; summary: string; curated: boolean;
  attribution: StateLink | null; technique_count: number; activity_30d: number; last_activity_at: string | null; is_favourite: boolean;
}
export interface Activity {
  id: number; source_type: string; source_name: string; title: string; summary: string; url: string | null;
  published_at: string; occurred_at: string | null; countries: CountryRef[]; attributed_countries: CountryRef[];
  sectors: string[]; tags: string[]; effect: string | null; ioc_count: number;
  groups: (GroupRef & { match_method: string; matched_text: string })[];
}
export interface HistoryItem {
  date: string; end_date: string | null; precision: string; title: string; description: string; kind: string;
  origin: string; source_name: string | null; source_url: string | null;
}
export interface GroupDetail extends GroupRef {
  attack_id: string | null; mitre_url: string | null; aliases: { alias: string; source: string }[];
  summary: string | null; description: string; motivation: string | null; first_seen: string | null; sources: string[];
  target_countries: CountryRef[]; target_sectors: string[]; state_links: StateLink[];
  relations: { group: GroupRef; relation: string; direction: string; description: string | null; confidence: string; source_name: string | null; source_url: string | null }[];
  history: HistoryItem[]; techniques_by_tactic: Record<string, { id: string; name: string }[]>; technique_count: number;
  software: { id: string; name: string; type: string }[]; activity_monthly: { month: string; count: number }[];
  recent_activity: Activity[]; hybrid_conflicts: { slug: string; name: string; links: number }[]; is_favourite: boolean;
}
export interface Stats {
  days: number;
  totals: { events_24h: number; events_7d: number; events_period: number; groups_active_7d: number; iocs_7d: number };
  daily: { date: string; count: number }[];
  by_country: (CountryRef & { count: number })[];
  by_group: { slug: string; name: string; country: string | null; count: number }[];
  by_effect: { effect: string; count: number }[];
  by_source: { source: string; count: number }[];
  heatmap: { weeks: string[]; groups: { slug: string; name: string; country: string | null; counts: number[] }[] };
}
export interface GraphNode {
  id: string; type: "group" | "state"; label: string; slug?: string; code?: string; kind?: string; motivation?: string | null;
  country?: string | null; activity_30d?: number; favourite?: boolean; context?: boolean; groups?: number;
}
export interface GraphEdge {
  source: string; target: string; type: "attribution" | "relation" | "targets"; relation?: string; confidence?: string;
  origin?: string; agency?: string | null; description?: string | null;
}
export interface Military {
  id: number; source: string; date: string; country: CountryRef | null; location: string | null; lat: number | null; lon: number | null;
  event_type: string; sub_event_type: string | null; actors: string | null; fatalities: number | null; description: string; url: string | null; intensity: number;
}
export interface ConflictBrief {
  slug: string; name: string; status: string; description: string; start_date: string; end_date: string | null;
  theatre: CountryRef[]; parties: { name: string; countries: CountryRef[] }[]; window_days: number;
  kinetic_count: number; last_kinetic_date: string | null; kinetic_sources: string[]; link_counts: Record<string, number>;
}
export interface HybridLink {
  id: number; method: string; score: number; lag_days: number; date_basis: string; rationale: string; cyber: Activity; kinetic: Military;
}
export interface ConflictDetail extends ConflictBrief {
  window: { start: string; end: string };
  series: { date: string; cyber: number; kinetic: number; fatalities: number }[];
  lag_correlation: { lag: number; r: number | null; n: number }[];
  convergence_days: { date: string; cyber: number; kinetic: number }[];
  participants: (GroupRef & { sides: number[]; events: number; is_favourite: boolean })[];
  cyber_events: (Activity & { date: string; date_basis: string; sides: number[] })[];
  kinetic_events: Military[];
  links: HybridLink[];
}
export interface User { id: number; email: string; display_name: string; is_admin: boolean }
export interface SourceRow {
  key: string; name: string; kind: string; configured: boolean; healthy: boolean; last_run_at: string | null;
  last_success_at: string | null; last_error: string | null; items_last_run: number; hint: string | null;
}
