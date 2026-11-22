import { Link } from "react-router-dom";
import { useTitle } from "../lib/auth";
import { useQuery } from "@tanstack/react-query";
import { api, type ConflictBrief } from "../lib/api";
import { fmtDate, nf } from "../lib/format";
import { useTheme } from "../lib/theme";
import { Card, ErrorBox, Loading } from "../components/ui";

export default function Hybrid() {
  useTitle("Hybrid warfare");
  const q = useQuery({ queryKey: ["conflicts"], queryFn: () => api<ConflictBrief[]>("/api/hybrid/conflicts") });
  const { tokens: t } = useTheme();
  const groups = [
    { title: "Active theatres", items: q.data?.filter((c) => c.status === "active") ?? [] },
    { title: "Historical case files", items: q.data?.filter((c) => c.status !== "active") ?? [] },
  ];
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Hybrid warfare tracker</h1>
          <p>
            Cyber operations that run alongside conventional military action. For each theatre ShadowTrace aligns conflict-relevant
            cyber activity with kinetic events (ACLED, GDELT, curated), scores candidate pairs and measures whether cyber activity
            tends to lead or follow military action.
          </p>
        </div>
      </div>
      {q.error && <ErrorBox error={q.error} />}
      {q.isLoading && <Loading h={300} />}
      {groups.map((g) => g.items.length > 0 && (
        <section key={g.title} style={{ marginBottom: 24 }}>
          <h2 style={{ marginBottom: 12 }}>{g.title}</h2>
          <div className="group-grid">
            {g.items.map((c) => (
              <Link key={c.slug} to={`/hybrid/${c.slug}`} className="card group-card">
                <div className="top">
                  <div className="name">{c.name}</div>
                  <span className={`badge ${c.status === "active" ? "conf-medium" : "conf-low"}`}><span className="dot" />{c.status === "active" ? "Active" : "Historical"}</span>
                </div>
                <div className="secondary" style={{ fontSize: 13 }}>{c.parties.map((p) => p.name).join(" vs ")}</div>
                <div className="summary">{c.description}</div>
                <div className="foot" style={{ flexWrap: "wrap" }}>
                  <span>{fmtDate(c.start_date)} – {c.end_date ? fmtDate(c.end_date) : "ongoing"}</span>
                  <span><i className="swatch" style={{ background: t.kinetic }} /> {nf.format(c.kinetic_count)} kinetic</span>
                  <span><i className="swatch" style={{ background: t.cyber }} /> {(c.link_counts.curated ?? 0)} curated · {(c.link_counts.auto ?? 0)} auto links</span>
                </div>
              </Link>
            ))}
          </div>
        </section>
      ))}
      <Card title="How the correlation works">
        <ol className="secondary" style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
          <li><b>Relevant cyber events</b>: reports linked to a group (or state) attributed to a belligerent, aimed at the theatre or a party, or with no stated target.</li>
          <li><b>Kinetic events</b>: ACLED (curated by analysts), GDELT (machine-coded from news, noisier), plus curated anchor events.</li>
          <li><b>Pair score</b> = time proximity × geography × opposing-side attribution × effect severity × date certainty × kinetic intensity. The best three pairs per cyber event within ± the theatre window are kept.</li>
          <li><b>Lag correlation</b>: Pearson r between daily cyber and kinetic counts shifted by −7…+7 days. A positive lag means cyber activity precedes kinetic activity.</li>
        </ol>
        <p className="subtle" style={{ marginBottom: 0 }}>Scores are triage aids, not attribution: co-occurrence is not causation. Feed reports are dated by publication, so they lag the activity itself and are down-weighted accordingly.</p>
      </Card>
    </>
  );
}
