import { Link } from "react-router-dom";
import type { Activity } from "../lib/api";
import { EFFECT_LABEL, timeAgo, fmtDate } from "../lib/format";
import { IconExternal } from "../lib/icons";

const SOURCE_LABEL: Record<string, string> = { rss: "Report", otx: "OTX pulse", curated: "Curated" };

export default function ActivityItem({ a, showDate = false }: { a: Activity; showDate?: boolean }) {
  return (
    <article className="list-item">
      <div className="meta">
        <span title={new Date(a.published_at).toLocaleString()}>{showDate ? fmtDate(a.occurred_at ?? a.published_at) : timeAgo(a.published_at)}</span>
        <span>·</span>
        <span>{SOURCE_LABEL[a.source_type] ?? a.source_type} · {a.source_name}</span>
        {a.effect && <span className="chip">{EFFECT_LABEL[a.effect] ?? a.effect}</span>}
        {a.ioc_count > 0 && <span className="chip">{a.ioc_count} IOCs</span>}
      </div>
      <div className="title">
        {a.url ? <a href={a.url} target="_blank" rel="noopener noreferrer nofollow">{a.title} <IconExternal className="ext-icon" /></a> : a.title}
      </div>
      {a.summary && <div className="secondary" style={{ fontSize: 13 }}>{a.summary.length > 260 ? a.summary.slice(0, 260) + "…" : a.summary}</div>}
      <div className="chips">
        {a.groups.map((g) => (
          <Link key={g.slug} to={`/groups/${g.slug}`} className="chip" title={`Matched on “${g.matched_text}” (${g.match_method})`}>{g.name}</Link>
        ))}
        {a.attributed_countries.map((c) => <span key={"att" + c.code} className="chip" title="Attributed state">⚑ {c.name}</span>)}
        {a.countries.length > 0 && <span className="muted" style={{ fontSize: 12, alignSelf: "center" }}>→ {a.countries.map((c) => c.name).join(", ")}</span>}
      </div>
    </article>
  );
}
