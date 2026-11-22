import { useDeferredValue, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTitle } from "../lib/auth";
import { useQuery } from "@tanstack/react-query";
import { api, qs, type Activity } from "../lib/api";
import { useScope } from "../lib/scope";
import { EFFECT_LABEL } from "../lib/format";
import ActivityItem from "../components/ActivityItem";
import { Card, Empty, ErrorBox, FavouritesEmpty, Loading, ScopeToggle } from "../components/ui";

const PAGE = 30;

export default function ActivityPage() {
  useTitle("Activity feed");
  const [scope, setScope] = useScope();
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(0);
  const q = params.get("q") ?? "";
  const source = params.get("source") ?? "";
  const effect = params.get("effect") ?? "";
  const days = Number(params.get("days") ?? 90);
  const group = params.get("group") ?? "";
  const dq = useDeferredValue(q);

  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v); else p.delete(k);
    setParams(p, { replace: true });
    setPage(0);
  };

  const r = useQuery({
    queryKey: ["activity", scope, dq, source, effect, days, group, page],
    queryFn: () => api<{ total: number; items: Activity[] }>(`/api/activity${qs({ scope, q: dq, source_type: source, effect, days, group, limit: PAGE, offset: page * PAGE })}`),
    placeholderData: (prev) => prev,
  });
  const pages = r.data ? Math.ceil(r.data.total / PAGE) : 0;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Activity feed</h1>
          <p>Every report linked to a tracked group. Group links come from name/alias matching, the OTX adversary field, or curation; hover a group chip to see why it matched.</p>
        </div>
        <ScopeToggle scope={scope} setScope={setScope} />
      </div>
      <div className="toolbar" role="search">
        <input className="input" style={{ width: 240 }} placeholder="Search titles…" value={q} onChange={(e) => set("q", e.target.value)} aria-label="Search reports" />
        <select className="select" value={source} onChange={(e) => set("source", e.target.value)} aria-label="Source type">
          <option value="">All sources</option><option value="rss">Vendor / CERT reports</option><option value="otx">OTX pulses</option><option value="curated">Curated</option>
        </select>
        <select className="select" value={effect} onChange={(e) => set("effect", e.target.value)} aria-label="Effect">
          <option value="">Any effect</option>
          {Object.entries(EFFECT_LABEL).filter(([k]) => k !== "unknown").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="select" value={days} onChange={(e) => set("days", e.target.value)} aria-label="Period">
          <option value="7">7 days</option><option value="30">30 days</option><option value="90">90 days</option><option value="365">1 year</option><option value="3650">All</option>
        </select>
        {group && <button className="btn" onClick={() => set("group", "")}>Group: {group} ✕</button>}
      </div>
      {r.error && <ErrorBox error={r.error} />}
      <Card>
        {r.isLoading ? <Loading h={400} /> : r.data?.items.length ? (
          <>
            <p className="subtle" style={{ marginTop: 0 }}>{r.data.total} reports</p>
            <div className="list">{r.data.items.map((a) => <ActivityItem key={a.id} a={a} />)}</div>
            {pages > 1 && (
              <div className="toolbar" style={{ justifyContent: "center", marginTop: 16, marginBottom: 0 }}>
                <button className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>← Newer</button>
                <span className="muted">Page {page + 1} / {pages}</span>
                <button className="btn" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Older →</button>
              </div>
            )}
          </>
        ) : scope === "favourites" && !q ? <FavouritesEmpty /> : <Empty>No reports match.</Empty>}
      </Card>
    </>
  );
}
