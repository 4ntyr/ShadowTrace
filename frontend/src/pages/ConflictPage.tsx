import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { api, qs, type ConflictDetail } from "../lib/api";
import { useScope } from "../lib/scope";
import { useTheme } from "../lib/theme";
import { EFFECT_LABEL, fmtDate, nf } from "../lib/format";
import EChart from "../components/EChart";
import WorldMap, { type MapPoint } from "../components/WorldMap";
import { Card, Empty, ErrorBox, FavStar, Loading, ScopeToggle, Segmented, Stat } from "../components/ui";
import { esc, roundedTop, timeAxis, tooltip, valueAxis } from "../components/chartkit";
import { loadWorld } from "../lib/geo";
import { IconExternal } from "../lib/icons";

/** Correlation lag: corr(cyber[t], kinetic[t+lag]) — positive means cyber precedes kinetic. */
function lagText(lag: number) {
  if (lag === 0) return "same day";
  return lag > 0 ? `cyber leads by ${lag}d` : `cyber follows by ${-lag}d`;
}

/** Link lag = cyber date − kinetic date — positive means the cyber event came after. */
function linkTiming(lagDays: number) {
  if (lagDays === 0) return "same day";
  return lagDays > 0 ? `cyber ${lagDays}d after` : `cyber ${-lagDays}d before`;
}

const MIN_CORR_EVENTS = 10;

export default function ConflictPage() {
  const { slug = "" } = useParams();
  const [scope, setScope] = useScope();
  const [days, setDays] = useState(90);
  const { tokens: t } = useTheme();
  const q = useQuery({
    queryKey: ["conflict", slug, days, scope],
    queryFn: () => api<ConflictDetail>(`/api/hybrid/conflicts/${encodeURIComponent(slug)}${qs({ days, scope })}`),
    placeholderData: (prev) => prev,
  });
  const world = useQuery({ queryKey: ["world"], queryFn: loadWorld, staleTime: Infinity });
  const c = q.data;

  const convergenceAreas = useMemo(
    () => (c?.convergence_days ?? []).map((d) => [{ xAxis: d.date + "T00:00:00Z" }, { xAxis: d.date + "T23:59:59Z" }]),
    [c],
  );

  const seriesChart = (key: "cyber" | "kinetic"): EChartsOption | null => {
    if (!c) return null;
    const color = key === "cyber" ? t.cyber : t.kinetic;
    return {
      grid: { left: 40, right: 12, top: 10, bottom: key === "kinetic" ? 28 : 8 },
      tooltip: tooltip(t, { trigger: "axis", axisPointer: { type: "line", lineStyle: { color: t.axis } }, valueFormatter: (v: number) => `${v} events` }),
      xAxis: timeAxis(t, { min: c.window.start, max: c.window.end, axisLabel: { show: key === "kinetic", color: t.muted, fontSize: 11, hideOverlap: true } }),
      yAxis: valueAxis(t),
      series: [{
        type: "bar", name: key === "cyber" ? "Cyber events" : "Kinetic events", barMaxWidth: 10,
        data: c.series.map((d) => [d.date + "T12:00:00Z", d[key]]),
        itemStyle: { color, borderRadius: roundedTop },
        markArea: convergenceAreas.length ? { silent: true, itemStyle: { color: t.status.warning, opacity: 0.12 }, data: convergenceAreas as any } : undefined, // eslint-disable-line @typescript-eslint/no-explicit-any
      }],
    };
  };
  const cyberOpt = useMemo(() => seriesChart("cyber"), [c, t, convergenceAreas]); // eslint-disable-line react-hooks/exhaustive-deps
  const kinOpt = useMemo(() => seriesChart("kinetic"), [c, t, convergenceAreas]); // eslint-disable-line react-hooks/exhaustive-deps

  const lagOpt = useMemo<EChartsOption | null>(() => {
    if (!c) return null;
    return {
      grid: { left: 40, right: 12, top: 12, bottom: 40 },
      tooltip: tooltip(t, {
        trigger: "axis", axisPointer: { type: "shadow" },
        formatter: (ps: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
          const p = ps[0]; const row = c.lag_correlation[p.dataIndex];
          return `<b>${esc(lagText(row.lag))}</b><br/>r = ${row.r ?? "n/a"} (n=${row.n} days)`;
        },
      }),
      xAxis: { type: "category", data: c.lag_correlation.map((l) => (l.lag > 0 ? `+${l.lag}` : String(l.lag))), name: "lag (days)", nameLocation: "middle", nameGap: 26, nameTextStyle: { color: t.muted, fontSize: 11 }, axisTick: { show: false }, axisLine: { lineStyle: { color: t.axis } }, axisLabel: { color: t.muted, fontSize: 11 } },
      yAxis: valueAxis(t, { min: -1, max: 1, minInterval: 0, splitNumber: 4 }),
      series: [{
        type: "bar", barMaxWidth: 16,
        data: c.lag_correlation.map((l) => ({
          value: l.r ?? 0,
          itemStyle: { color: (l.r ?? 0) >= 0 ? t.divergingPos : t.divergingNeg, borderRadius: (l.r ?? 0) >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4] },
        })),
        markLine: { silent: true, symbol: "none", lineStyle: { color: t.axis }, data: [{ yAxis: 0 }], label: { show: false } },
      }],
    };
  }, [c, t]);

  const lanesOpt = useMemo<EChartsOption | null>(() => {
    if (!c) return null;
    const linkedKin = new Set(c.links.map((l) => l.kinetic.id));
    const kin = c.kinetic_events.filter((k) => linkedKin.has(k.id)).concat(c.kinetic_events.filter((k) => !linkedKin.has(k.id)).slice(0, 250));
    const lines = c.links.map((l) => ({
      coords: [[(l.cyber.occurred_at ?? l.cyber.published_at), "Cyber"], [l.kinetic.date + "T12:00:00Z", "Kinetic"]],
      raw: l,
      lineStyle: { color: l.method === "curated" ? t.text : t.muted, type: l.method === "curated" ? "solid" : "dashed", width: l.method === "curated" ? 1.6 : 1, opacity: l.method === "curated" ? 0.8 : 0.35 + 0.5 * l.score },
    }));
    return {
      grid: { left: 64, right: 16, top: 16, bottom: 30 },
      tooltip: tooltip(t, { trigger: "item" }),
      xAxis: timeAxis(t, { min: c.window.start, max: c.window.end }),
      yAxis: { type: "category", data: ["Kinetic", "Cyber"], axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: t.textSecondary, fontWeight: 600 }, splitLine: { show: true, lineStyle: { color: t.grid } } },
      series: [
        {
          type: "lines", coordinateSystem: "cartesian2d", data: lines as any, zlevel: 1, // eslint-disable-line @typescript-eslint/no-explicit-any
          tooltip: { formatter: (p: any) => `<b>${p.data.raw.method === "curated" ? "Curated link" : `Auto link · score ${p.data.raw.score}`}</b><br/>${esc(linkTiming(p.data.raw.lag_days))}<br/><span style="color:${t.muted}">${esc(p.data.raw.rationale)}</span>` }, // eslint-disable-line @typescript-eslint/no-explicit-any
        },
        {
          type: "scatter", name: "Kinetic events", symbol: "circle", zlevel: 2,
          data: kin.map((k) => ({ value: [k.date + "T12:00:00Z", "Kinetic", k.intensity], raw: k })),
          symbolSize: (v: any) => 6 + v[2] * 10, // eslint-disable-line @typescript-eslint/no-explicit-any
          itemStyle: { color: t.kinetic, opacity: 0.7, borderColor: t.surface, borderWidth: 1.5 },
          tooltip: { formatter: (p: any) => `<b>${esc(p.data.raw.description)}</b><br/>${fmtDate(p.data.raw.date)} · ${esc(p.data.raw.location ?? "")}<br/><span style="color:${t.muted}">${esc(p.data.raw.source.toUpperCase())} · ${esc(p.data.raw.sub_event_type ?? p.data.raw.event_type)}</span>` }, // eslint-disable-line @typescript-eslint/no-explicit-any
        },
        {
          type: "scatter", name: "Cyber events", symbol: "diamond", symbolSize: 12, zlevel: 3,
          data: c.cyber_events.map((e) => ({ value: [e.date + "T12:00:00Z", "Cyber"], raw: e })),
          itemStyle: { color: t.cyber, borderColor: t.surface, borderWidth: 1.5 },
          tooltip: { formatter: (p: any) => `<b>${esc(p.data.raw.title)}</b><br/>${fmtDate(p.data.raw.date)} · ${p.data.raw.date_basis === "occurred" ? "date of activity" : "report date"}${p.data.raw.groups.length ? `<br/>${esc(p.data.raw.groups.map((g: any) => g.name).join(", "))}` : ""}` }, // eslint-disable-line @typescript-eslint/no-explicit-any
        },
      ],
      dataZoom: [{ type: "inside", xAxisIndex: 0, filterMode: "none" }],
    } as EChartsOption;
  }, [c, t]);

  const points = useMemo<MapPoint[]>(() => {
    if (!c) return [];
    const pts: MapPoint[] = c.kinetic_events.filter((k) => k.lat != null && k.lon != null).slice(0, 800).map((k) => ({
      lon: k.lon!, lat: k.lat!, size: k.intensity, name: k.description, detail: `${fmtDate(k.date)} · ${k.location ?? ""} · ${k.source.toUpperCase()}`, series: "kinetic",
    }));
    const centroids = world.data?.centroids ?? {};
    c.cyber_events.forEach((e, i) => {
      const target = e.countries.find((x) => centroids[x.code]) ?? null;
      if (!target) return;
      const [lon, lat] = centroids[target.code];
      const a = (i * 137.5 * Math.PI) / 180; const r = 0.25 + (i % 7) * 0.12; // golden-angle jitter so stacked events stay visible
      pts.push({ lon: lon + r * Math.cos(a), lat: lat + r * Math.sin(a), size: 0.4, name: e.title, detail: `${fmtDate(e.date)} · cyber → ${target.name}`, series: "cyber" });
    });
    return pts;
  }, [c, world.data]);

  if (q.isLoading) return <Loading h={600} />;
  if (q.error || !c) return <ErrorBox error={q.error ?? new Error("Not found")} />;

  const best = c.lag_correlation.filter((l) => l.r != null).sort((a, b) => Math.abs(b.r!) - Math.abs(a.r!))[0];
  const curated = c.links.filter((l) => l.method === "curated").length;
  const auto = c.links.length - curated;
  const totalCyber = c.series.reduce((s, d) => s + d.cyber, 0);
  const totalKin = c.series.reduce((s, d) => s + d.kinetic, 0);
  const theatre = c.theatre.map((x) => x.code);
  const enoughData = totalCyber >= MIN_CORR_EVENTS && totalKin >= MIN_CORR_EVENTS;

  return (
    <>
      <div className="page-head">
        <div>
          <p style={{ margin: "0 0 6px" }}><Link to="/hybrid">← Hybrid warfare</Link></p>
          <h1>{c.name}</h1>
          <p>{c.description}</p>
          <div className="chips" style={{ marginTop: 8 }}>
            {c.parties.map((p, i) => <span key={i} className="chip">Side {i + 1}: {p.name} ({p.countries.map((x) => x.code).join(", ")})</span>)}
            <span className="chip">Window ±{c.window_days}d</span>
            <span className="chip">Kinetic sources: {c.kinetic_sources.length ? c.kinetic_sources.join(", ").toUpperCase() : "none yet"}</span>
          </div>
        </div>
        <div className="toolbar" style={{ margin: 0 }}>
          <ScopeToggle scope={scope} setScope={setScope} />
          {c.status === "active" && (
            <Segmented label="Period" value={days} onChange={setDays} options={[{ value: 30, label: "30d" }, { value: 90, label: "90d" }, { value: 180, label: "180d" }, { value: 365, label: "1y" }]} />
          )}
        </div>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 16 }}>
        <Stat label="Conflict-relevant cyber events" value={nf.format(totalCyber)} hint={`${fmtDate(c.window.start)} – ${fmtDate(c.window.end)}`} />
        <Stat label="Kinetic events" value={nf.format(totalKin)} hint={c.last_kinetic_date ? `latest ${fmtDate(c.last_kinetic_date)}` : "connect ACLED/GDELT"} />
        <Stat label="Cyber ↔ kinetic links" value={nf.format(c.links.length)} hint={`${curated} curated · ${auto} auto-scored`} />
        <Stat
          label="Strongest lag correlation"
          value={enoughData && best && Math.abs(best.r!) >= 0.2 ? `r = ${best.r!.toFixed(2)}` : "—"}
          hint={!enoughData ? `Needs ≥ ${MIN_CORR_EVENTS} cyber and kinetic events` : best && Math.abs(best.r!) >= 0.2 ? lagText(best.lag) : "No meaningful correlation in window"}
        />
      </div>

      <div className="grid grid-3" style={{ marginBottom: 16 }}>
        <Card className="span-2" title="Daily activity" sub={c.convergence_days.length ? `Shaded: ${c.convergence_days.length} convergence day(s) where both series spiked above their 14-day baseline` : "Both series share the time axis; hover to compare"}>
          <h3 className="secondary" style={{ fontSize: 12, fontWeight: 600, margin: "0 0 2px" }}><i className="swatch" style={{ background: t.cyber }} /> Cyber events per day</h3>
          {cyberOpt && <EChart option={cyberOpt} height={130} group={`conf-${slug}`} ariaLabel="Bar chart of cyber events per day" />}
          <h3 className="secondary" style={{ fontSize: 12, fontWeight: 600, margin: "10px 0 2px" }}><i className="swatch" style={{ background: t.kinetic }} /> Kinetic events per day</h3>
          {kinOpt && <EChart option={kinOpt} height={150} group={`conf-${slug}`} ariaLabel="Bar chart of kinetic events per day" />}
        </Card>
        <Card title="Lead / lag correlation" sub="Pearson r of daily counts; positive lag means cyber precedes kinetic">
          {!enoughData && <div className="notice" style={{ marginBottom: 8 }}>Only {totalCyber} cyber and {totalKin} kinetic events in this window, so r is not statistically meaningful yet.</div>}
          {lagOpt && <EChart option={lagOpt} height={enoughData ? 260 : 200} ariaLabel="Bar chart of correlation by lag" />}
          <div className="legend"><span><i className="swatch" style={{ background: t.divergingPos }} />positive r</span><span><i className="swatch" style={{ background: t.divergingNeg }} />negative r</span></div>
        </Card>
      </div>

      <Card title="Event lanes" sub="Each line pairs a cyber event with a kinetic event. Solid lines are curated, dashed are auto-scored (opacity = score). Scroll to zoom." className="">
        <div className="legend" style={{ marginBottom: 6 }}>
          <span><svg width="12" height="12"><path d="M6 0 12 6 6 12 0 6z" fill={t.cyber} /></svg>Cyber event</span>
          <span><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill={t.kinetic} /></svg>Kinetic event (size = intensity)</span>
        </div>
        {lanesOpt && <EChart option={lanesOpt} height={220} ariaLabel="Timeline of cyber and kinetic events with links" />}
      </Card>

      <div className="grid grid-3" style={{ margin: "16px 0" }}>
        <Card className="span-2" title="Theatre map" sub="Kinetic events at reported coordinates; cyber events at the targeted country (jittered)">
          <div className="legend" style={{ marginBottom: 6 }}>
            <span><svg width="12" height="12"><path d="M6 0 12 6 6 12 0 6z" fill={t.cyber} /></svg>Cyber</span>
            <span><svg width="12" height="12"><circle cx="6" cy="6" r="5" fill={t.kinetic} /></svg>Kinetic</span>
            <span><svg width="14" height="10"><rect x="1" y="1" width="12" height="8" fill="none" stroke={t.text} /></svg>Theatre</span>
          </div>
          <WorldMap points={points} highlight={theatre} focus={theatre} height={420} ariaLabel={`Map of events in the ${c.name} theatre`} />
        </Card>
        <Card title="Cyber actors involved" sub="Groups with conflict-relevant activity in this window">
          {c.participants.length ? (
            <div className="list">
              {c.participants.map((p) => (
                <div key={p.slug} className="list-item" style={{ gridTemplateColumns: "1fr auto", alignItems: "center" }}>
                  <div>
                    <Link to={`/groups/${p.slug}`}><strong>{p.name}</strong></Link>
                    <div className="meta">{p.sides.length ? p.sides.map((s) => c.parties[s]?.name).join(", ") + " side" : "side unclear"} · {p.events} event(s)</div>
                  </div>
                  <FavStar slug={p.slug} on={p.is_favourite} name={p.name} />
                </div>
              ))}
            </div>
          ) : <Empty>No attributed cyber activity in this window.</Empty>}
        </Card>
      </div>

      <Card title="Linked pairs" sub="Highest-scoring cyber ↔ kinetic pairs">
        {c.links.length ? (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Link</th><th>Cyber event</th><th>Kinetic event</th><th>Timing</th><th>Why</th></tr></thead>
              <tbody>
                {c.links.map((l) => (
                  <tr key={l.id}>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <span className={`badge ${l.method === "curated" ? "curated" : "auto"}`}>{l.method === "curated" ? "Curated" : "Auto"}</span>
                      {l.method === "auto" && <div style={{ marginTop: 6 }}><span className="scorebar" title={`score ${l.score}`}><i style={{ width: `${l.score * 100}%` }} /></span> <span className="mono muted">{l.score.toFixed(2)}</span></div>}
                    </td>
                    <td style={{ minWidth: 220 }}>
                      <div style={{ fontWeight: 600 }}>{l.cyber.url ? <a href={l.cyber.url} target="_blank" rel="noopener noreferrer nofollow">{l.cyber.title} <IconExternal className="ext-icon" /></a> : l.cyber.title}</div>
                      <div className="meta muted" style={{ fontSize: 12 }}>
                        {fmtDate(l.cyber.occurred_at ?? l.cyber.published_at)}{l.cyber.effect ? ` · ${EFFECT_LABEL[l.cyber.effect] ?? l.cyber.effect}` : ""}
                        {l.cyber.groups.length > 0 && <> · {l.cyber.groups.map((g, i) => <span key={g.slug}>{i > 0 && ", "}<Link to={`/groups/${g.slug}`}>{g.name}</Link></span>)}</>}
                      </div>
                    </td>
                    <td style={{ minWidth: 200 }}>
                      <div>{l.kinetic.url ? <a href={l.kinetic.url} target="_blank" rel="noopener noreferrer nofollow">{l.kinetic.description}</a> : l.kinetic.description}</div>
                      <div className="muted" style={{ fontSize: 12 }}>{fmtDate(l.kinetic.date)} · {l.kinetic.location ?? l.kinetic.country?.name} · {l.kinetic.source.toUpperCase()}</div>
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>{linkTiming(l.lag_days)}<div className="muted" style={{ fontSize: 12 }}>{l.date_basis === "occurred" ? "activity date" : "report date"}</div></td>
                    <td className="secondary" style={{ fontSize: 12.5, minWidth: 220 }}>{l.rationale}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty>No linked pairs in this window yet. Links appear as feeds and kinetic sources accumulate data.</Empty>}
      </Card>
      <p className="subtle" style={{ marginTop: 12 }}>
        Correlation scores are analyst triage aids, not attribution. GDELT events are machine-coded from news and can be mis-geocoded; ACLED is preferred when configured.
      </p>
    </>
  );
}
