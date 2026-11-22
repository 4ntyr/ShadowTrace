import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, GraphChart, HeatmapChart, LineChart, LinesChart, MapChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent, GeoComponent, GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent,
  TooltipComponent, VisualMapComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";

echarts.use([
  BarChart, GraphChart, HeatmapChart, LineChart, LinesChart, MapChart, ScatterChart,
  DataZoomComponent, GeoComponent, GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent,
  TooltipComponent, VisualMapComponent, CanvasRenderer,
]);

export { echarts };

interface Props {
  option: EChartsOption;
  height: number | string;
  group?: string; // charts in the same group share tooltip/axis pointer
  onClick?: (params: any) => void; // eslint-disable-line @typescript-eslint/no-explicit-any
  ariaLabel: string;
}

export default function EChart({ option, height, group, onClick, ariaLabel }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const clickRef = useRef(onClick);
  clickRef.current = onClick;

  useEffect(() => {
    if (!ref.current) return;
    const c = echarts.init(ref.current, undefined, { renderer: "canvas" });
    chart.current = c;
    c.on("click", (p) => clickRef.current?.(p));
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(ref.current);
    return () => { ro.disconnect(); c.dispose(); chart.current = null; };
  }, []);

  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    c.setOption({ animationDuration: 300, ...option }, { notMerge: true });
    if (group) { c.group = group; echarts.connect(group); }
  }, [option, group]);

  return <div ref={ref} role="img" aria-label={ariaLabel} style={{ width: "100%", height }} />;
}
