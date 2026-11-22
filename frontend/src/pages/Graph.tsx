import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTitle } from "../lib/auth";
import { useQuery } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { api, qs, type GraphEdge, type GraphNode } from "../lib/api";
import { useScope } from "../lib/scope";
import { STATE_SLOTS, stateColor, useTheme } from "../lib/theme";
import { RELATION_LABEL, cap } from "../lib/format";
import EChart from "../components/EChart";
import { Card, ConfidenceBadge, ErrorBox, FavouritesEmpty, Loading, ScopeToggle } from "../components/ui";
import { esc, tooltip } from "../components/chartkit";

const CONF_OPACITY: Record<string, number> = { confirmed: 0.95, high: 0.7, medium: 0.5, low: 0.28 };

export default function Graph() {
  useTitle("Relations");
  const [scope, setScope] = useScope();
  const [minConf, setMinConf] = useState("low");
  const [targets, setTargets] = useState(false);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const { tokens: t } = useTheme();

  const q = useQuery({
    queryKey: ["graph", scope, minConf, targets],
    queryFn: () => api<{ nodes: GraphNode[]; edges: GraphEdge[] }>(`/api/graph${qs({ scope, min_confidence: minConf, include_targets: targets })}`),
  });

  const option = useMemo<EChartsOption | null>(() => {
    if (!q.data) return null;
    const { nodes, edges } = q.data;
    const degree = new Map<string, number>();
    for (const e of edges) { degree.set(e.source, (degree.get(e.source) ?? 0) + 1); degree.set(e.target, (degree.get(e.target) ?? 0) + 1); }
    return {
      tooltip: tooltip(t, {
        formatter: (p: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
          if (p.dataType === "edge") {
            const e: GraphEdge = p.data.raw;
            const lbl = e.type === "targets" ? "Targets" : (RELATION_LABEL[e.relation ?? ""] ?? cap(e.relation));
            return `${esc(p.data.sourceLabel)} → ${esc(p.data.targetLabel)}<br/><b>${esc(lbl)}</b>${e.confidence ? ` · ${esc(e.confidence)}` : ""}${e.agency ? `<br/>${esc(e.agency)}` : ""}${e.description ? `<br/><span style="color:${t.muted}">${esc(e.description)}</span>` : ""}`;
          }
          const n: GraphNode = p.data.raw;
          return n.type === "state" ? `<b>${esc(n.label)}</b><br/>${n.groups} attributed group(s)` : `<b>${esc(n.label)}</b>${n.favourite ? " ★" : ""}<br/>${n.activity_30d ?? 0} reports in 30 days`;
        },
      }),
      series: [{
        type: "graph", layout: "force", roam: true, draggable: true,
        force: { repulsion: 90, edgeLength: [30, 90], gravity: 0.22, friction: 0.2 },
        emphasis: { focus: "adjacency", lineStyle: { width: 3 } },
        labelLayout: { hideOverlap: true },
        scaleLimit: { min: 0.3, max: 4 },
        data: nodes.map((n) => {
          const isState = n.type === "state";
          const color = isState ? stateColor(t, n.code) : stateColor(t, n.country);
          const size = isState ? 22 + Math.sqrt(n.groups ?? 1) * 5 : 8 + Math.sqrt(n.activity_30d ?? 0) * 4 + Math.min(6, degree.get(n.id) ?? 0);
          return {
            id: n.id, name: n.label, raw: n,
            symbol: isState ? "roundRect" : "circle",
            symbolSize: size,
            itemStyle: {
              color: isState ? t.surface : color,
              borderColor: isState ? color : n.favourite ? t.status.warning : t.surface,
              borderWidth: isState ? 3 : n.favourite ? 3 : 1.5,
              opacity: n.context ? 0.55 : 1,
            },
            label: {
              show: isState || n.favourite || (n.activity_30d ?? 0) > 0 || (degree.get(n.id) ?? 0) > 2,
              position: isState ? "inside" : "right",
              color: isState ? t.text : t.textSecondary, fontSize: isState ? 11 : 11, fontWeight: isState ? 700 : 400,
              formatter: isState ? (n.code ?? n.label) : (n.favourite ? "★ " : "") + n.label,
            },
          };
        }),
        links: edges.map((e) => {
          const src = nodes.find((n) => n.id === e.source)!;
          const tgt = nodes.find((n) => n.id === e.target)!;
          const base = {
            source: e.source, target: e.target, raw: e, sourceLabel: src?.label, targetLabel: tgt?.label,
          };
          if (e.type === "relation") return { ...base, lineStyle: { color: t.text, width: 2, opacity: 0.75, curveness: 0.2 } };
          if (e.type === "targets") return { ...base, lineStyle: { color: t.kinetic, width: 1, type: "dotted", opacity: 0.35 } };
          return {
            ...base,
            lineStyle: {
              color: stateColor(t, tgt?.code), width: e.confidence === "confirmed" ? 2 : 1.2,
              opacity: CONF_OPACITY[e.confidence ?? "low"], type: e.origin === "mitre_text" ? "dashed" : "solid",
            },
          };
        }),
      }],
    } as EChartsOption;
  }, [q.data, t]);

  const stateLegend = Object.keys(STATE_SLOTS);
  const groupCount = q.data?.nodes.filter((n) => n.type === "group").length ?? 0;
  const neighbours = selected && q.data ? q.data.edges.filter((e) => e.source === selected.id || e.target === selected.id) : [];
  const labelOf = (id: string) => q.data?.nodes.find((n) => n.id === id)?.label ?? id;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Relations</h1>
          <p>How groups connect to states (attribution) and to each other (shared agency, overlaps, collaboration). Drag to rearrange, scroll to zoom, click a node for details.</p>
        </div>
        <ScopeToggle scope={scope} setScope={setScope} />
      </div>
      <div className="toolbar">
        <label className="check">Min. attribution confidence
          <select className="select" value={minConf} onChange={(e) => setMinConf(e.target.value)}>
            <option value="low">Low (incl. auto-extracted)</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="confirmed">Confirmed only</option>
          </select>
        </label>
        <label className="check"><input type="checkbox" checked={targets} onChange={(e) => setTargets(e.target.checked)} /> Show targeted states</label>
        <span className="muted" style={{ marginLeft: "auto", fontSize: 12 }}>{groupCount} groups</span>
      </div>
      {q.error && <ErrorBox error={q.error} />}
      {scope === "favourites" && q.data && groupCount === 0 ? <Card><FavouritesEmpty /></Card> : (
        <div className="card" style={{ position: "relative", padding: 0 }}>
          {option ? <EChart option={option} height="72vh" ariaLabel="Force-directed graph of groups and states" onClick={(p) => p.dataType === "node" && setSelected(p.data.raw)} /> : <Loading h={600} />}
          {selected && (
            <div className="card side-panel">
              <div className="card-head">
                <h2>{selected.label}</h2>
                <button className="btn ghost" onClick={() => setSelected(null)} aria-label="Close details">✕</button>
              </div>
              {selected.type === "group" ? (
                <>
                  <p className="secondary" style={{ marginTop: 0 }}>{selected.activity_30d ?? 0} reports in the last 30 days{selected.context ? " · shown as context for a favourite" : ""}</p>
                  <Link className="btn primary" to={`/groups/${selected.slug}`}>Open profile</Link>
                </>
              ) : <p className="secondary" style={{ marginTop: 0 }}>{selected.groups} attributed group(s) in view</p>}
              <h3 style={{ margin: "14px 0 6px" }}>Connections ({neighbours.length})</h3>
              <div className="list" style={{ fontSize: 13 }}>
                {neighbours.map((e, i) => {
                  const other = e.source === selected.id ? e.target : e.source;
                  return (
                    <div key={i} className="list-item">
                      <span>{labelOf(other)}</span>
                      <span className="meta">
                        {e.type === "targets" ? "Targets" : RELATION_LABEL[e.relation ?? ""] ?? cap(e.relation)}
                        {e.confidence && <ConfidenceBadge level={e.confidence} />}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
      <Card className="legend-card" title="Legend">
        <div className="legend" style={{ marginBottom: 10 }}>
          {stateLegend.map((c) => <span key={c}><i className="swatch" style={{ background: stateColor(t, c) }} />{c}</span>)}
          <span><i className="swatch" style={{ background: t.muted }} />Other</span>
        </div>
        <div className="legend">
          <span><svg width="16" height="16"><rect x="2" y="2" width="12" height="12" rx="3" fill="none" stroke={t.text} strokeWidth="2" /></svg>State</span>
          <span><svg width="16" height="16"><circle cx="8" cy="8" r="6" fill={t.textSecondary} /></svg>Group (size = recent activity)</span>
          <span><svg width="16" height="16"><circle cx="8" cy="8" r="5" fill={t.textSecondary} stroke={t.status.warning} strokeWidth="2.5" /></svg>Favourite</span>
          <span><svg width="28" height="10"><line x1="0" y1="5" x2="28" y2="5" stroke={t.textSecondary} strokeWidth="2" /></svg>Curated attribution (opacity = confidence)</span>
          <span><svg width="28" height="10"><line x1="0" y1="5" x2="28" y2="5" stroke={t.textSecondary} strokeWidth="1.2" strokeDasharray="4 3" /></svg>Auto-extracted attribution</span>
          <span><svg width="28" height="10"><path d="M0 8 Q14 0 28 8" fill="none" stroke={t.text} strokeWidth="2" /></svg>Group ↔ group relation</span>
          {targets && <span><svg width="28" height="10"><line x1="0" y1="5" x2="28" y2="5" stroke={t.kinetic} strokeWidth="1.5" strokeDasharray="1 3" /></svg>Targets</span>}
        </div>
      </Card>
    </>
  );
}
