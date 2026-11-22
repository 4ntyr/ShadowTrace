import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTitle } from "../lib/auth";
import { useQuery } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { api, qs, type Activity, type ConflictBrief, type Stats } from "../lib/api";
import { useScope } from "../lib/scope";
import { useTheme, stateColor } from "../lib/theme";
import { EFFECT_LABEL, fmtDate, nf } from "../lib/format";
import EChart from "../components/EChart";
import WorldMap from "../components/WorldMap";
import ActivityItem from "../components/ActivityItem";
import { Card, Empty, ErrorBox, FavouritesEmpty, Loading, ScopeToggle, Segmented, Stat } from "../components/ui";
import { esc, roundedTop, timeAxis, tooltip, valueAxis } from "../components/chartkit";

export default function Dashboard() {
  useTitle("Dashboard");
  const [scope, setScope] = useScope();
  const [days, setDays] = useState(90);
  const { tokens: t } = useTheme();

  const stats = useQuery({ queryKey: ["stats", scope, days], queryFn: () => api<Stats>(`/api/activity/stats${qs({ scope, days })}`) });
  const feed = useQuery({
    queryKey: ["activity", scope, "latest"],
    queryFn: () => api<{ total: number; items: Activity[] }>(`/api/activity${qs({ scope, days: 365, limit: 12 })}`),
  });
  const conflicts = useQuery({ queryKey: ["conflicts"], queryFn: () => api<ConflictBrief[]>("/api/hybrid/conflicts") });

  const daily = useMemo<EChartsOption | null>(() => {
    if (!stats.data) return null;
    return {
      grid: { left: 36, right: 12, top: 12, bottom: 28 },
      tooltip: tooltip(t, { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v: number) => `${v} reports` }),
      xAxis: timeAxis(t),
      yAxis: valueAxis(t),
      series: [{
        type: "bar", name: "Reports", barMaxWidth: 10,
        data: stats.data.daily.map((d) => [d.date, d.count]),
        itemStyle: { color: t.cyber, borderRadius: roundedTop },
      }],
    };
  }, [stats.data, t]);

  const heat = useMemo<EChartsOption | null>(() => {
    const h = stats.data?.heatmap;
    if (!h || !h.groups.length) return null;
    const data: [number, number, number][] = [];
    h.groups.forEach((g, y) => g.counts.forEach((c, x) => data.push([x, y, c])));
    const max = Math.max(1, ...data.map((d) => d[2]));
    return {
      grid: { left: 140, right: 16, top: 8, bottom: 40 },
      tooltip: tooltip(t, {
        formatter: (p: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
          const g = h.groups[p.value[1]];
          return `<b>${esc(g.name)}</b>${g.country ? ` · ${esc(g.country)}` : ""}<br/>Week of ${fmtDate(h.weeks[p.value[0]])}: <b>${p.value[2]}</b> reports`;
        },
      }),
      xAxis: { type: "category", data: h.weeks.map((w) => fmtDate(w)), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.muted, fontSize: 11, hideOverlap: true }, splitArea: { show: false } },
      yAxis: { type: "category", data: h.groups.map((g) => g.name), inverse: true, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.textSecondary, fontSize: 12, width: 130, overflow: "truncate" } },
      visualMap: { min: 0, max, show: false, inRange: { color: [t.neutral, ...t.sequential.slice(2)] } },
      series: [{ type: "heatmap", data, itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 3 }, emphasis: { itemStyle: { borderColor: t.text, borderWidth: 1 } } }],
    };
  }, [stats.data, t]);

  const s = stats.data;
  const favEmpty = scope === "favourites" && s && s.totals.events_period === 0 && s.by_group.length === 0;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Threat activity overview</h1>
          <p>Reported APT activity from vendor, CERT and OTX feeds, matched to tracked groups.{scope === "favourites" && " Showing your favourite groups only."}</p>
        </div>
        <div className="toolbar" style={{ margin: 0 }}>
          <ScopeToggle scope={scope} setScope={setScope} />
          <Segmented label="Period" value={days} onChange={setDays} options={[{ value: 30, label: "30d" }, { value: 90, label: "90d" }, { value: 180, label: "180d" }, { value: 365, label: "1y" }]} />
        </div>
      </div>

      {stats.error && <ErrorBox error={stats.error} />}

      <div className="grid grid-4" style={{ marginBottom: 16 }}>
        <Stat label="Reports · last 24 h" value={s ? nf.format(s.totals.events_24h) : "–"} />
        <Stat label="Reports · last 7 days" value={s ? nf.format(s.totals.events_7d) : "–"} hint={s ? `${nf.format(s.totals.events_period)} in the last ${days} days` : undefined} />
        <Stat label="Active groups · 7 days" value={s ? nf.format(s.totals.groups_active_7d) : "–"} />
        <Stat label="Indicators shared · 7 days" value={s ? nf.format(s.totals.iocs_7d) : "–"} hint="From OTX pulses" />
      </div>

      {favEmpty ? <Card><FavouritesEmpty /></Card> : (
        <div className="grid grid-3">
          <Card className="span-2" title="Reports per day" sub="Publications mentioning a tracked group">
            {daily ? <EChart option={daily} height={220} ariaLabel="Bar chart of reports per day" /> : <Loading h={220} />}
          </Card>
          <Card title="By effect" sub="Keyword-classified">
            {s ? (s.by_effect.length ? s.by_effect.map((e) => (
              <BarRow key={e.effect} label={EFFECT_LABEL[e.effect] ?? e.effect} value={e.count} max={s.by_effect[0].count} color={t.cyber} />
            )) : <Empty>No reports yet.</Empty>) : <Loading h={160} />}
          </Card>

          <Card className="span-2" title="Targeted countries" sub="Countries named as victims in reports (attacker origin excluded)">
            {s ? <WorldMap values={s.by_country} height={340} ariaLabel="World map of targeted countries" /> : <Loading h={340} />}
          </Card>
          <Card title="Most reported groups" sub={`Last ${days} days`}>
            {s ? (s.by_group.length ? s.by_group.slice(0, 10).map((g) => (
              <BarRow key={g.slug} label={<Link to={`/groups/${g.slug}`}>{g.name}</Link>} value={g.count} max={s.by_group[0].count} color={stateColor(t, g.country)} />
            )) : <Empty>No group activity in this period.</Empty>) : <Loading h={300} />}
            {s && s.by_group.length > 0 && <p className="subtle" style={{ marginTop: 8 }}>Bar colour = attributed state (see Relations legend).</p>}
          </Card>

          <Card className="span-2" title="Weekly activity by group" sub="Top groups, reports per week. Darker cells mean more reports">
            {stats.isLoading ? <Loading h={320} /> : heat ? <EChart option={heat} height={Math.max(160, 28 * (s?.heatmap.groups.length ?? 0) + 50)} ariaLabel="Heatmap of weekly reports per group" /> : <Empty>No activity to chart yet.</Empty>}
          </Card>
          <Card title="Hybrid-warfare theatres" actions={<Link to="/hybrid">Open tracker →</Link>}>
            {conflicts.data ? (
              <div className="list">
                {conflicts.data.filter((c) => c.status === "active").map((c) => (
                  <Link key={c.slug} to={`/hybrid/${c.slug}`} className="list-item" style={{ color: "inherit", textDecoration: "none" }}>
                    <span className="title">{c.name}</span>
                    <span className="meta">
                      <span><span className="swatch" style={{ background: t.kinetic }} /> {nf.format(c.kinetic_count)} kinetic events</span>
                      <span>{(c.link_counts.curated ?? 0) + (c.link_counts.auto ?? 0)} cyber↔kinetic links</span>
                    </span>
                  </Link>
                ))}
              </div>
            ) : <Loading h={160} />}
          </Card>

          <Card className="span-2" title="Latest reports" actions={<Link to={`/activity${scope === "favourites" ? "?scope=favourites" : ""}`}>All activity →</Link>}>
            {feed.isLoading ? <Loading h={300} /> : feed.data?.items.length ? (
              <div className="list">{feed.data.items.map((a) => <ActivityItem key={a.id} a={a} />)}</div>
            ) : <Empty>No reports yet. The worker polls feeds every 30 minutes.</Empty>}
          </Card>
          <Card title="Sources" sub="Where reports came from">
            {s ? s.by_source.map((x) => <BarRow key={x.source} label={x.source.toUpperCase()} value={x.count} max={s.by_source[0].count} color={t.cyber} />) : <Loading h={100} />}
            <p className="subtle" style={{ marginTop: 10 }}><Link to="/sources">Feed health →</Link></p>
          </Card>
        </div>
      )}
    </>
  );
}

function BarRow({ label, value, max, color }: { label: React.ReactNode; value: number; max: number; color: string }) {
  return (
    <div className="bar-row">
      <span className="name">{label}</span>
      <span className="track"><span className="fill" style={{ width: `${(100 * value) / Math.max(1, max)}%`, background: color, display: "block" }} /></span>
      <span className="num">{value}</span>
    </div>
  );
}
