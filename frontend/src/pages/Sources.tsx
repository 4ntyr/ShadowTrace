import { useQuery } from "@tanstack/react-query";
import { api, type SourceRow } from "../lib/api";
import { nf, timeAgo } from "../lib/format";
import { IconAlert, IconCheck, IconOff } from "../lib/icons";
import { Card, ErrorBox, Loading, Stat } from "../components/ui";

function Status({ s }: { s: SourceRow }) {
  if (!s.configured) return <span className="status idle"><IconOff />Not configured</span>;
  if (s.last_error) return <span className="status critical"><IconAlert />Failing</span>;
  if (!s.last_success_at) return <span className="status idle"><IconOff />Never run</span>;
  const stale = Date.now() - new Date(s.last_success_at).getTime() > 1000 * 3600 * 12 && s.kind !== "mitre";
  return stale ? <span className="status warning"><IconAlert />Stale</span> : <span className="status good"><IconCheck />Healthy</span>;
}

const KIND_LABEL: Record<string, string> = { rss: "RSS", otx: "OTX", acled: "ACLED", gdelt: "GDELT", mitre: "MITRE", correlation: "Engine" };

export default function Sources() {
  const q = useQuery({
    queryKey: ["sources"],
    queryFn: () => api<{ sources: SourceRow[]; counts: Record<string, number>; keys: { otx: boolean; acled: boolean } }>("/api/sources"),
    refetchInterval: 60_000,
  });
  const d = q.data;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Data sources</h1>
          <p>Connector health. The background worker polls RSS every 30 min, GDELT every 15 min, OTX hourly, ACLED every 6 h and MITRE ATT&amp;CK weekly, then re-runs the correlation engine.</p>
        </div>
      </div>
      {q.error && <ErrorBox error={q.error} />}
      {d && (
        <div className="grid grid-4" style={{ marginBottom: 16 }}>
          <Stat label="Tracked groups" value={nf.format(d.counts.groups)} />
          <Stat label="Activity reports" value={nf.format(d.counts.activity_events)} />
          <Stat label="Kinetic events" value={nf.format(d.counts.military_events)} />
          <Stat label="Keyed sources" value={`${Number(d.keys.otx) + Number(d.keys.acled)} / 2`} hint={`OTX ${d.keys.otx ? "on" : "off"} · ACLED ${d.keys.acled ? "on" : "off"}`} />
        </div>
      )}
      <Card>
        {q.isLoading ? <Loading h={400} /> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Source</th><th>Type</th><th>Status</th><th>Last success</th><th className="num">Items last run</th><th>Details</th></tr></thead>
              <tbody>
                {d?.sources.map((s) => (
                  <tr key={s.key}>
                    <td><strong>{s.name}</strong><div className="mono muted">{s.key}</div></td>
                    <td>{KIND_LABEL[s.kind] ?? s.kind}</td>
                    <td><Status s={s} /></td>
                    <td title={s.last_success_at ?? ""}>{timeAgo(s.last_success_at)}</td>
                    <td className="num">{s.items_last_run}</td>
                    <td className="secondary" style={{ fontSize: 12.5, maxWidth: 420 }}>{s.last_error ?? s.hint ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
