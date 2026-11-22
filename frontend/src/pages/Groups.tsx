import { useDeferredValue } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, qs, type CountryRef, type GroupListItem } from "../lib/api";
import { useScope } from "../lib/scope";
import { cap, timeAgo } from "../lib/format";
import { stateColor, useTheme } from "../lib/theme";
import { AttributionLine, ConfidenceBadge, Empty, ErrorBox, FavStar, FavouritesEmpty, Loading, ScopeToggle } from "../components/ui";

const MOTIVATIONS = ["espionage", "destructive", "financial", "mixed", "influence", "hacktivism", "prepositioning"];
const KINDS = ["apt", "criminal", "hacktivist", "persona"];

export default function Groups() {
  const [scope, setScope] = useScope();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const country = params.get("country") ?? "";
  const motivation = params.get("motivation") ?? "";
  const kind = params.get("kind") ?? "";
  const sort = params.get("sort") ?? "activity";
  const dq = useDeferredValue(q);
  const { tokens: t } = useTheme();

  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v); else p.delete(k);
    setParams(p, { replace: true });
  };

  const countries = useQuery({ queryKey: ["countries"], queryFn: () => api<(CountryRef & { groups: number })[]>("/api/countries") });
  const groups = useQuery({
    queryKey: ["groups", scope, dq, country, motivation, kind, sort],
    queryFn: () => api<{ total: number; items: GroupListItem[] }>(`/api/groups${qs({ scope, q: dq, country, motivation, kind, sort })}`),
    placeholderData: (prev) => prev,
  });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Threat groups</h1>
          <p>{groups.data ? `${groups.data.total} groups` : "Groups"} from MITRE ATT&amp;CK, enriched with curated attribution, history and relations. Star a group to follow it.</p>
        </div>
        <ScopeToggle scope={scope} setScope={setScope} />
      </div>
      <div className="toolbar" role="search">
        <input className="input" style={{ width: 260 }} placeholder="Search name, alias or G-ID…" value={q} onChange={(e) => set("q", e.target.value)} aria-label="Search groups" />
        <select className="select" value={country} onChange={(e) => set("country", e.target.value)} aria-label="Attributed state">
          <option value="">All states</option>
          {countries.data?.map((c) => <option key={c.code} value={c.code}>{c.name} ({c.groups})</option>)}
        </select>
        <select className="select" value={motivation} onChange={(e) => set("motivation", e.target.value)} aria-label="Motivation">
          <option value="">Any motivation</option>
          {MOTIVATIONS.map((m) => <option key={m} value={m}>{cap(m)}</option>)}
        </select>
        <select className="select" value={kind} onChange={(e) => set("kind", e.target.value)} aria-label="Actor type">
          <option value="">Any type</option>
          {KINDS.map((m) => <option key={m} value={m}>{m === "apt" ? "APT" : cap(m)}</option>)}
        </select>
        <select className="select" value={sort} onChange={(e) => set("sort", e.target.value)} aria-label="Sort">
          <option value="activity">Most active (30d)</option>
          <option value="recent">Most recent report</option>
          <option value="name">Name</option>
        </select>
      </div>

      {groups.error && <ErrorBox error={groups.error} />}
      {groups.isLoading ? <Loading h={400} /> : groups.data?.items.length ? (
        <div className="group-grid">
          {groups.data.items.map((g) => (
            <Link key={g.slug} to={`/groups/${g.slug}`} className="card group-card">
              <div className="top">
                <div style={{ minWidth: 0 }}>
                  <div className="name">
                    <span className="swatch" style={{ background: stateColor(t, g.origin_country?.code), marginRight: 8 }} aria-hidden="true" />
                    {g.name} {g.attack_id && <span className="mono muted">{g.attack_id}</span>}
                  </div>
                  {g.aliases.length > 0 && <div className="aliases" title={g.aliases.join(", ")}>aka {g.aliases.join(", ")}</div>}
                </div>
                <FavStar slug={g.slug} on={g.is_favourite} name={g.name} />
              </div>
              <div style={{ fontSize: 13 }}><AttributionLine link={g.attribution} /></div>
              <div className="chips">
                {g.attribution && <ConfidenceBadge level={g.attribution.confidence} />}
                {g.motivation && <span className="chip">{cap(g.motivation)}</span>}
                {g.kind !== "apt" && <span className="chip">{cap(g.kind)}</span>}
              </div>
              <div className="summary">{g.summary}</div>
              <div className="foot">
                <span>{g.activity_30d} report{g.activity_30d === 1 ? "" : "s"} · 30d</span>
                <span>Last: {timeAgo(g.last_activity_at)}</span>
                {g.technique_count > 0 && <span>{g.technique_count} techniques</span>}
              </div>
            </Link>
          ))}
        </div>
      ) : scope === "favourites" && !q ? <FavouritesEmpty /> : <Empty>No groups match these filters.</Empty>}
    </>
  );
}
