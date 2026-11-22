// Shared chart styling: recessive grid/axes, thin marks, 4px rounded data-ends, hover tooltips.
import type { ChartTokens } from "../lib/theme";

export function tooltip(t: ChartTokens, extra: Record<string, unknown> = {}) {
  return {
    backgroundColor: t.surface,
    borderColor: t.axis,
    borderWidth: 1,
    padding: [8, 10],
    textStyle: { color: t.text, fontSize: 12 },
    extraCssText: "border-radius:8px;box-shadow:0 6px 18px rgba(0,0,0,.25);",
    confine: true,
    ...extra,
  };
}

export function timeAxis(t: ChartTokens, extra: Record<string, unknown> = {}) {
  return {
    type: "time" as const,
    axisLine: { lineStyle: { color: t.axis } },
    axisTick: { show: false },
    axisLabel: { color: t.muted, fontSize: 11, hideOverlap: true },
    splitLine: { show: false },
    ...extra,
  };
}

export function valueAxis(t: ChartTokens, extra: Record<string, unknown> = {}) {
  return {
    type: "value" as const,
    minInterval: 1,
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: t.muted, fontSize: 11 },
    splitLine: { lineStyle: { color: t.grid } },
    ...extra,
  };
}

export const roundedTop = [4, 4, 0, 0];

export function esc(s: string | null | undefined): string {
  return (s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}
