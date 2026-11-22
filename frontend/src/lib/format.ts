const dateFmt = new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric" });
const monthFmt = new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short" });

export function fmtDate(iso: string | null | undefined, precision: string = "day"): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? iso + "T12:00:00Z" : iso);
  if (precision === "year") return String(d.getUTCFullYear());
  if (precision === "month") return monthFmt.format(d);
  return dateFmt.format(d);
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} d ago`;
  return fmtDate(iso);
}

export const nf = new Intl.NumberFormat();

export const RELATION_LABEL: Record<string, string> = {
  operated_by: "Operated by",
  sponsor: "State-sponsored",
  aligned: "Aligned with",
  alleged: "Alleged link",
  attributed: "Attributed (auto)",
  based_in: "Based in (auto)",
  subgroup: "Subgroup",
  overlap: "Overlap",
  collaboration: "Collaboration",
  shared_tooling: "Shared tooling",
  same_agency: "Same agency",
  persona: "Persona / front",
};

export const EFFECT_LABEL: Record<string, string> = {
  disruptive: "Disruptive",
  ddos: "DDoS",
  influence: "Influence",
  espionage: "Espionage",
  unknown: "Unclassified",
};

export const cap = (s: string | null | undefined) => (s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ") : "");
