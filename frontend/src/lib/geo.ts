// World geometry for maps (lazy-loaded). Features are keyed by ISO alpha-2 so API data joins directly.
import type { Feature, FeatureCollection, Geometry, Position } from "geojson";

let cache: Promise<{ geojson: FeatureCollection; centroids: Record<string, [number, number]> }> | null = null;

function ringArea(r: Position[]): number {
  let a = 0;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) a += (r[j][0] * r[i][1]) - (r[i][0] * r[j][1]);
  return a / 2;
}
function ringCentroid(r: Position[]): [number, number] {
  let x = 0, y = 0, a = 0;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
    const f = r[j][0] * r[i][1] - r[i][0] * r[j][1];
    x += (r[j][0] + r[i][0]) * f; y += (r[j][1] + r[i][1]) * f; a += f;
  }
  if (a === 0) return [r[0][0], r[0][1]];
  return [x / (3 * a), y / (3 * a)];
}
function centroid(g: Geometry): [number, number] | null {
  const polys = g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : [];
  let best: Position[] | null = null, bestA = 0;
  for (const p of polys) { const a = Math.abs(ringArea(p[0])); if (a > bestA) { bestA = a; best = p[0]; } }
  return best ? ringCentroid(best) : null;
}

/** Rings crossing the antimeridian (Chukotka, Fiji, Aleutians) would draw streaks across the map;
 *  shift their western-hemisphere points by +360° so each ring stays contiguous. */
function unwrap(g: Geometry): Geometry {
  const fixRing = (r: Position[]) => {
    let min = Infinity, max = -Infinity;
    for (const p of r) { if (p[0] < min) min = p[0]; if (p[0] > max) max = p[0]; }
    return max - min > 180 ? r.map((p) => (p[0] < 0 ? [p[0] + 360, p[1]] : p)) : r;
  };
  if (g.type === "Polygon") return { ...g, coordinates: g.coordinates.map(fixRing) };
  if (g.type === "MultiPolygon") return { ...g, coordinates: g.coordinates.map((poly) => poly.map(fixRing)) };
  return g;
}

export function loadWorld() {
  if (!cache) {
    cache = (async () => {
      const [{ feature }, topo, countries] = await Promise.all([
        import("topojson-client"),
        import("world-atlas/countries-50m.json"),
        import("i18n-iso-countries"),
      ]);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const t = (topo as any).default ?? topo;
      const fc = feature(t, t.objects.countries) as unknown as FeatureCollection;
      const lib = (countries as any).default ?? countries;
      const features: Feature[] = [];
      const centroids: Record<string, [number, number]> = {};
      for (const f of fc.features) {
        const num = f.id != null ? String(f.id).padStart(3, "0") : null;
        let code = num ? lib.numericToAlpha2(num) : undefined;
        if (!code && f.properties?.name === "Kosovo") code = "XK";
        if (!code || code === "AQ") continue;
        f.geometry = unwrap(f.geometry);
        features.push({ ...f, properties: { ...f.properties, name: code, label: f.properties?.name } });
        const c = centroid(f.geometry);
        if (c) centroids[code] = c;
      }
      return { geojson: { type: "FeatureCollection", features }, centroids };
    })();
  }
  return cache;
}
