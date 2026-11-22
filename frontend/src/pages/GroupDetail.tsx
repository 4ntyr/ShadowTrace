import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { api, type GroupDetail as GD } from "../lib/api";
import { RELATION_LABEL, cap, fmtDate } from "../lib/format";
import { stateColor, useTheme } from "../lib/theme";
import EChart from "../components/EChart";
import ActivityItem from "../components/ActivityItem";
import { Card, ConfidenceBadge, Empty, ErrorBox, FavStar, Loading } from "../components/ui";
import { roundedTop, tooltip, valueAxis } from "../components/chartkit";
import { IconExternal } from "../lib/icons";

const TACTIC_ORDER = [
  "reconnaissance", "resource-development", "initial-access", "execution", "persistence", "privilege-escalation",
  "defense-evasion", "credential-access", "discovery", "lateral-movement", "collection", "command-and-control",
  "exfiltration", "impact",
];
type Tab = "profile" | "history" | "activity" | "techniques";

export default function GroupDetail() {
  const { slug = "" } = useParams();
  const [tab, setTab] = useState<Tab>("profile");
  const { tokens: t } = useTheme();
  const q = useQuery({ queryKey: ["group", slug], queryFn: () => api<GD>(`/api/groups/${encodeURIComponent(slug)}`) });
  const g = q.data;

  const monthly = useMemo<EChartsOption | null>(() => {
    if (!g) return null;
    return {
      grid: { left: 32, right: 8, top: 10, bottom: 24 },
      tooltip: tooltip(t, { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v: number) => `${v} reports` }),
      xAxis: { type: "category", data: g.activity_monthly.map((m) => m.month), axisTick: { show: false }, axisLine: { lineStyle: { color: t.axis } }, axisLabel: { color: t.muted, fontSize: 11 } },
      yAxis: valueAxis(t),
      series: [{ type: "bar", name: "Reports", data: g.activity_monthly.map((m) => m.count), barMaxWidth: 18, itemStyle: { color: t.cyber, borderRadius: roundedTop } }],
    };
  }, [g, t]);

  if (q.isLoading) return <Loading h={500} />;
  if (q.error || !g) return <ErrorBox error={q.error ?? new Error("Not found")} />;

  const tactics = Object.keys(g.techniques_by_tactic).sort((a, b) => TACTIC_ORDER.indexOf(a) - TACTIC_ORDER.indexOf(b));

  return (
    <>
      <div className="page-head">
        <div style={{ minWidth: 0 }}>
          <p style={{ margin: "0 0 6px" }}><Link to="/groups">← Groups</Link></p>
          <h1 style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <span className="swatch" style={{ background: stateColor(t, g.origin_country?.code), width: 14, height: 14 }} aria-hidden="true" />
            {g.name}
            {g.attack_id && <span className="mono muted" style={{ fontSize: 14 }}>{g.attack_id}</span>}
            <FavStar slug={g.slug} on={g.is_favourite} name={g.name} />
          </h1>
          <div className="chips" style={{ marginTop: 8 }}>
            {g.motivation && <span className="chip">{cap(g.motivation)}</span>}
            <span className="chip">{g.kind === "apt" ? "APT" : cap(g.kind)}</span>
            {g.first_seen && <span className="chip">First seen {fmtDate(g.first_seen, "year")}</span>}
            {g.mitre_url && <a className="chip" href={g.mitre_url} target="_blank" rel="noopener noreferrer">MITRE ATT&amp;CK <IconExternal className="ext-icon" /></a>}
          </div>
        </div>
      </div>

      <div className="grid grid-3" style={{ marginBottom: 16 }}>
        <Card className="span-2" title="Attribution">
          {g.state_links.length ? (
            <div className="list">
              {g.state_links.map((l, i) => (
                <div key={i} className="list-item">
                  <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                    <span className="swatch" style={{ background: stateColor(t, l.country.code) }} aria-hidden="true" />
                    <strong>{l.country.name}</strong>
                    <span className="secondary">{RELATION_LABEL[l.relation] ?? cap(l.relation)}</span>
                    <ConfidenceBadge level={l.confidence} />
                    {l.origin === "mitre_text" && <span className="badge auto">auto-extracted</span>}
                  </div>
                  {l.agency && <div>{l.agency}</div>}
                  <div className="meta">
                    {l.note && <span>{l.note}</span>}
                    {l.source_name && (l.source_url
                      ? <a href={l.source_url} target="_blank" rel="noopener noreferrer">{l.source_name} <IconExternal className="ext-icon" /></a>
                      : <span>Source: {l.source_name}</span>)}
                  </div>
                </div>
              ))}
            </div>
          ) : <Empty>No public state attribution recorded.</Empty>}
        </Card>
        <Card title="Also known as">
          <div className="chips">{g.aliases.map((a) => <span key={a.alias} className="chip">{a.alias}</span>)}</div>
          {g.target_countries.length > 0 && (<>
            <h3 style={{ margin: "16px 0 8px" }}>Primary targets</h3>
            <div className="chips">{g.target_countries.map((c) => <span key={c.code} className="chip">{c.name}</span>)}</div>
          </>)}
          {g.target_sectors.length > 0 && (<>
            <h3 style={{ margin: "16px 0 8px" }}>Sectors</h3>
            <div className="chips">{g.target_sectors.map((s) => <span key={s} className="chip">{s}</span>)}</div>
          </>)}
        </Card>
      </div>

      <div className="tabs" role="tablist">
        {(["profile", "history", "activity", "techniques"] as Tab[]).map((k) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>
            {{ profile: "Profile & relations", history: `History (${g.history.length})`, activity: `Activity (${g.recent_activity.length})`, techniques: `Techniques & tools (${g.technique_count})` }[k]}
          </button>
        ))}
      </div>

      {tab === "profile" && (
        <div className="grid grid-3">
          <Card className="span-2" title="Profile">
            {g.summary && <p style={{ marginTop: 0, fontSize: 15 }}>{g.summary}</p>}
            {g.description && <div className="secondary" style={{ whiteSpace: "pre-line" }}>{g.description}</div>}
            {!g.summary && !g.description && <Empty>No profile yet.</Empty>}
            <p className="subtle" style={{ marginTop: 12 }}>Sources: {g.sources.map((s) => (s === "mitre" ? "MITRE ATT&CK" : "ShadowTrace curation")).join(" + ")}</p>
          </Card>
          <div className="grid" style={{ alignContent: "start" }}>
            <Card title="Related groups" actions={<Link to="/graph">Graph →</Link>}>
              {g.relations.length ? (
                <div className="list">
                  {g.relations.map((r, i) => (
                    <div key={i} className="list-item">
                      <div><Link to={`/groups/${r.group.slug}`}><strong>{r.group.name}</strong></Link> <span className="secondary">· {RELATION_LABEL[r.relation] ?? cap(r.relation)}</span></div>
                      {r.description && <div className="secondary" style={{ fontSize: 13 }}>{r.description}</div>}
                      <div className="meta"><ConfidenceBadge level={r.confidence} />{r.source_name && <span>{r.source_name}</span>}</div>
                    </div>
                  ))}
                </div>
              ) : <Empty>No curated relations.</Empty>}
            </Card>
            {g.hybrid_conflicts.length > 0 && (
              <Card title="Hybrid-warfare involvement">
                {g.hybrid_conflicts.map((c) => (
                  <div key={c.slug} className="list-item"><Link to={`/hybrid/${c.slug}`}>{c.name}</Link><span className="meta">{c.links} cyber↔kinetic links</span></div>
                ))}
              </Card>
            )}
          </div>
        </div>
      )}

      {tab === "history" && (
        <Card title="Timeline" sub="Curated milestones and MITRE ATT&CK campaigns, oldest first">
          {g.history.length ? (
            <div className="timeline">
              {g.history.map((h, i) => (
                <div key={i} className={`tl-item kind-${h.kind}`}>
                  <div className="when">
                    {fmtDate(h.date, h.precision)}{h.end_date ? ` – ${fmtDate(h.end_date, "month")}` : ""} · {cap(h.kind)}
                    {h.origin === "mitre_campaign" && " · MITRE campaign"}
                  </div>
                  <div className="what">{h.title}</div>
                  {h.description && <div className="desc">{h.description}</div>}
                  {(h.source_name || h.source_url) && (
                    <div className="when">{h.source_url ? <a href={h.source_url} target="_blank" rel="noopener noreferrer">{h.source_name ?? "Source"} <IconExternal className="ext-icon" /></a> : h.source_name}</div>
                  )}
                </div>
              ))}
            </div>
          ) : <Empty>No recorded history yet.</Empty>}
        </Card>
      )}

      {tab === "activity" && (
        <div className="grid">
          <Card title="Reports per month" sub="Last 12 months">
            {monthly && <EChart option={monthly} height={200} ariaLabel={`Bar chart of monthly reports about ${g.name}`} />}
          </Card>
          <Card title="Recent reports">
            {g.recent_activity.length ? <div className="list">{g.recent_activity.map((a) => <ActivityItem key={a.id} a={a} showDate />)}</div> : <Empty>No reports collected yet.</Empty>}
          </Card>
        </div>
      )}

      {tab === "techniques" && (
        <div className="grid">
          <Card title="ATT&CK techniques by tactic">
            {tactics.length ? (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 16 }}>
                {tactics.map((tac) => (
                  <div key={tac}>
                    <h3 style={{ marginBottom: 6 }}>{cap(tac.replace(/-/g, " "))} <span className="muted">({g.techniques_by_tactic[tac].length})</span></h3>
                    <ul style={{ margin: 0, paddingLeft: 16, fontSize: 13 }}>
                      {g.techniques_by_tactic[tac].map((x) => (
                        <li key={x.id}><a href={`https://attack.mitre.org/techniques/${x.id.replace(".", "/")}/`} target="_blank" rel="noopener noreferrer"><span className="mono">{x.id}</span></a> {x.name}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            ) : <Empty>No techniques mapped.</Empty>}
          </Card>
          <Card title="Software">
            {g.software.length ? (
              <div className="chips">
                {g.software.map((s) => <a key={s.id} className="chip" href={`https://attack.mitre.org/software/${s.id}/`} target="_blank" rel="noopener noreferrer" title={s.type}>{s.name}</a>)}
              </div>
            ) : <Empty>No software mapped.</Empty>}
          </Card>
        </div>
      )}
    </>
  );
}
