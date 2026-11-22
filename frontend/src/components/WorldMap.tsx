import { useEffect, useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import EChart, { echarts } from "./EChart";
import { Loading } from "./ui";
import { loadWorld } from "../lib/geo";
import { useTheme } from "../lib/theme";
import { esc, tooltip } from "./chartkit";

export interface MapPoint {
  lon: number; lat: number; size: number; name: string; detail?: string; series: "kinetic" | "cyber";
}

interface Props {
  values?: { code: string; name: string; count: number }[]; // choropleth
  points?: MapPoint[];
  highlight?: string[]; // countries outlined (e.g. conflict theatre)
  focus?: string[]; // zoom to these countries
  height: number;
  ariaLabel: string;
  valueLabel?: string;
}

let registered = false;

export default function WorldMap({ values = [], points = [], highlight = [], focus, height, ariaLabel, valueLabel = "Reports" }: Props) {
  const { tokens: t } = useTheme();
  const [world, setWorld] = useState<Awaited<ReturnType<typeof loadWorld>> | null>(null);
  useEffect(() => {
    loadWorld().then((w) => {
      if (!registered) { echarts.registerMap("world", w.geojson as any); registered = true; } // eslint-disable-line @typescript-eslint/no-explicit-any
      setWorld(w);
    });
  }, []);

  const option = useMemo<EChartsOption | null>(() => {
    if (!world) return null;
    const max = Math.max(1, ...values.map((v) => v.count));
    const byCode = new Map(values.map((v) => [v.code, v]));
    // sqrt scale so a single dominant country doesn't flatten everything else; skip the two darkest steps.
    const ramp = t.sequential.slice(2);
    const seqColor = (f: number) => ramp[Math.min(ramp.length - 1, Math.floor(Math.sqrt(f) * (ramp.length - 1) + 0.5))];
        let center: [number, number] | undefined;
    let zoom = 1.15;
    const fit = (xs: number[], ys: number[], minSpan: number) => {
      center = [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];
      const span = Math.max(Math.max(...xs) - Math.min(...xs), (Math.max(...ys) - Math.min(...ys)) * 1.6, minSpan);
      zoom = Math.min(14, 300 / span);
    };
    const located = points.filter((p) => p.series === "kinetic");
    if (focus?.length && located.length >= 3) {
      // Frame the bulk of the events (5th–95th percentile) so a few mis-geocoded points don't zoom out.
      const q = (arr: number[], f: number) => arr[Math.min(arr.length - 1, Math.max(0, Math.round(f * (arr.length - 1))))];
      const xs = located.map((p) => p.lon).sort((a, b) => a - b), ys = located.map((p) => p.lat).sort((a, b) => a - b);
      fit([q(xs, 0.05), q(xs, 0.95)], [q(ys, 0.05), q(ys, 0.95)], 10);
    } else if (focus?.length) {
      const cs = focus.map((c) => world.centroids[c]).filter(Boolean);
      if (cs.length) fit(cs.map((c) => c[0]), cs.map((c) => c[1]), 14);
    }
    const pointSeries = (kind: "kinetic" | "cyber") => ({
      type: "scatter" as const,
      coordinateSystem: "geo" as const,
      name: kind === "kinetic" ? "Kinetic event" : "Cyber event",
      symbol: kind === "kinetic" ? "circle" : "diamond",
      data: points.filter((p) => p.series === kind).map((p) => ({ value: [p.lon, p.lat, p.size], name: p.name, detail: p.detail })),
      symbolSize: (v: number[]) => 7 + Math.sqrt(v[2]) * 10,
      itemStyle: {
        color: kind === "kinetic" ? t.kinetic : t.cyber,
        opacity: kind === "kinetic" ? 0.55 : 0.9,
        borderColor: t.surface, borderWidth: 1.5,
      },
      emphasis: { scale: 1.4, itemStyle: { opacity: 1 } },
      zlevel: kind === "cyber" ? 2 : 1,
      tooltip: {
        formatter: (p: any) => `<b>${esc(p.data.name)}</b>${p.data.detail ? `<br/><span style="color:${t.muted}">${esc(p.data.detail)}</span>` : ""}`, // eslint-disable-line @typescript-eslint/no-explicit-any
      },
    });
    return {
      tooltip: tooltip(t, { trigger: "item" }),
      geo: {
        map: "world", roam: true, zoom, center, scaleLimit: { min: 1, max: 20 },
        itemStyle: { areaColor: t.neutral === "#383835" ? "#242422" : "#ecebe7", borderColor: t.axis, borderWidth: 0.4 },
        emphasis: { disabled: true },
        regions: [
          ...values.filter((v) => v.count > 0).map((v) => ({
            name: v.code,
            itemStyle: { areaColor: seqColor(v.count / max), ...(highlight.includes(v.code) ? { borderColor: t.text, borderWidth: 1.2 } : {}) },
          })),
          ...highlight.filter((c) => !byCode.has(c)).map((c) => ({ name: c, itemStyle: { borderColor: t.text, borderWidth: 1.2 } })),
        ],
        tooltip: {
          show: values.length > 0,
          formatter: (p: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
            const v = byCode.get(p.name);
            return v ? `<b>${esc(v.name)}</b><br/>${valueLabel}: <b>${v.count}</b>` : "";
          },
        },
      },
      series: [
        ...(points.length ? [pointSeries("kinetic"), pointSeries("cyber")] : []),
      ],
    } as EChartsOption;
  }, [world, values, points, highlight, focus, t, valueLabel]);

  if (!option) return <Loading h={height} />;
  const max = Math.max(0, ...values.map((v) => v.count));
  return (
    <>
      <EChart option={option} height={height} ariaLabel={ariaLabel} />
      {max > 0 && (
        <div className="legend" style={{ marginTop: 6, alignItems: "center" }}>
          <span>1</span>
          <span style={{ width: 140, height: 10, borderRadius: 3, background: `linear-gradient(90deg, ${t.sequential.slice(2).join(",")})` }} />
          <span>{max} {max === 1 ? valueLabel.toLowerCase().replace(/s$/, "") : valueLabel.toLowerCase()}</span>
        </div>
      )}
    </>
  );
}
