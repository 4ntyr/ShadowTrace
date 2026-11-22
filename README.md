# ShadowTrace: APT & Hybrid-Warfare Tracker

ShadowTrace is a browser-based tracker for state-linked threat actors (APT groups). It covers

* **Group intelligence**: profiles, aliases, ATT&CK techniques and software for ~180 groups from
  MITRE ATT&CK, enriched with a curated layer: state attribution with agency and confidence, sourced
  history timelines and group↔group relations.
* **Relations graph**: an interactive network of groups ↔ states (attribution, optionally
  targeting) and groups ↔ groups (same agency, subgroup, overlap, collaboration, personas).
* **Current activity**: a near-real-time feed of vendor/CERT reports and OTX pulses matched to
  groups, shown as a daily trend, a targeted-country choropleth, a group×week heatmap and a feed.
* **Favourites**: user accounts, a star on any group, and an *All / Favourites* scope on every view
  (dashboard, groups, graph, activity, hybrid tracker).
* **Hybrid-warfare tracker**: per conflict theatre, cyber operations aligned with kinetic military
  events (ACLED, GDELT, curated anchors), scored cyber↔kinetic pairs, lead/lag correlation,
  "convergence days" and a theatre map.

| Dashboard | Hybrid conflict view |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Hybrid](docs/screenshots/hybrid-conflict.png) |
| **Relations graph** | **Group profile** |
| ![Relations](docs/screenshots/relations.png) | ![Group](docs/screenshots/group-detail.png) |

---

## Quick start (Docker)

```bash
cp .env.example .env
```

Edit `.env`: set `ST_SECRET_KEY` and `POSTGRES_PASSWORD`, and optionally add OTX/ACLED keys. Then:

```bash
docker compose up -d --build
```

Open <http://localhost:8080>. On first start the worker loads the bundled MITRE ATT&CK snapshot and
the curation files, backfills 24 h of GDELT events and polls all feeds. Activity accumulates from
then on; RSS feeds only expose their latest items, so the dashboard fills up over the first days.

Make a user an admin (reserved for future curation tools):

```bash
docker compose exec api python -m app.cli make-admin you@example.org
```

## Local development

Requirements: Python 3.12+, Node 20+, PostgreSQL 14+ (SQLite works for quick experiments).

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export ST_DATABASE_URL=postgresql+psycopg://shadowtrace:shadowtrace@localhost:5432/shadowtrace
python -m app.cli init           # tables + MITRE snapshot + curation
python -m app.cli run rss        # or: otx | gdelt | acled | correlate | mitre
uvicorn app.main:app --reload    # API on :8000
python -m app.worker             # (separate shell) scheduler for all feeds
pytest -q                        # SQLite by default; set ST_TEST_DATABASE_URL for Postgres
```

```bash
cd frontend
npm install
npm run dev                      # http://localhost:5173, proxies /api to :8000
```

## Architecture

```
            ┌──────────── web (nginx) ────────────┐
 browser ──▶│ React + ECharts SPA   /api ─────────┼──▶ api (FastAPI) ──┐
            └─────────────────────────────────────┘                    ▼
                                                                  PostgreSQL
   MITRE ATT&CK ─┐                                                     ▲
   RSS (vendors, CERTs) ─┤                                             │
   AlienVault OTX ───────┼──▶ worker (APScheduler) ── connectors ──────┤
   GDELT 2.0 events ─────┤        └── correlation engine ──────────────┘
   ACLED ────────────────┘
```

| Path | What |
|---|---|
| `backend/app/models.py` | Schema: groups, aliases, state links, relations, history, activity, military events, conflicts, hybrid links, users, favourites |
| `backend/app/ingest/` | Connectors (`mitre`, `rss`, `otx`, `gdelt`, `acled`), alias matcher, attribution extractor, curation loader |
| `backend/app/correlation.py` | Cyber↔kinetic scoring, daily series, lag correlation, convergence detection |
| `backend/app/routers/` | REST API (`/api/groups`, `/api/graph`, `/api/activity`, `/api/hybrid`, `/api/auth`, `/api/favourites`, `/api/sources`) |
| `backend/data/curation/` | **Curated intelligence** (YAML): `groups.yaml`, `conflicts.yaml`, `feeds.yaml` |
| `backend/data/mitre_snapshot.json.gz` | Offline ATT&CK snapshot (refreshed weekly by the worker; rebuild with `python -m scripts.build_mitre_snapshot`) |
| `frontend/src/pages/` | Dashboard, Groups, Group detail, Relations, Activity, Hybrid list, Conflict view, Sources, Auth |

## Data sources

| Source | Key | Used for | Schedule |
|---|---|---|---|
| MITRE ATT&CK Enterprise | none | groups, aliases, techniques, software, campaigns | weekly |
| Vendor & CERT RSS (ESET, Microsoft, Unit 42, Securelist, Check Point, SentinelLabs, Talos, Proofpoint, Recorded Future, The Record, CERT-UA, CERT-FR, UK NCSC, CISA, …) | none | activity (kept only when a tracked group is mentioned) | 30 min |
| AlienVault OTX | `ST_OTX_API_KEY` (free) | activity with adversary, targeted countries, sectors, IOC counts | 60 min |
| GDELT 2.0 events | none | kinetic events (machine-coded; filtered to military CAMEO codes in theatres, aggregated per day/place) | 15 min |
| ACLED | `ST_ACLED_USERNAME`/`ST_ACLED_PASSWORD` (free registration) | kinetic events (analyst-curated, with fatalities) | 6 h |

The *Data sources* page shows each connector's health. A connector without a key shows as "Not
configured" and is skipped; nothing breaks. The ACLED connector targets ACLED's current OAuth API
(`/oauth/token`, `/api/acled/read`). It has not been run against live ACLED credentials yet, so check
the Data sources page after adding yours.

## How things work

**Group matching.** Report text is matched against every group name and alias with word boundaries.
Aliases that are ordinary words ("Snake", "Play", "Sidewinder", "Ghostwriter", …) only match with
their original capitalisation *and* next to an actor keyword ("Snake malware", "Play ransomware"). An
alias claimed by two groups is ignored. Each activity item records *why* it matched (hover a group chip).

**Attribution.** Curated attributions (`groups.yaml`) carry relation (operated by / sponsor / aligned /
alleged), agency, confidence (confirmed = government attribution, indictment or sanctions; high;
medium; low) and a source. For ATT&CK groups without curation, the origin state is extracted from the
first sentence of the MITRE description and stored as **low confidence, auto-extracted**. The UI flags
these with dashed lines in the graph and a badge on the profile.

**Hybrid correlation.** For each conflict:

1. *Relevant cyber events*: activity linked to a group or state aligned with a belligerent, aimed at
   the theatre or a party, or with no stated target.
2. *Kinetic events*: ACLED, GDELT and curated anchors inside the theatre and conflict dates.
3. *Pair score* = time proximity × geography × opposing-side attribution × effect (disruptive > DDoS >
   influence > espionage) × date certainty (activity date vs. report date) × kinetic intensity. The
   top 3 pairs per cyber event within ±`window_days` are stored as *auto* links. *Curated* links from
   `conflicts.yaml` are never overwritten.
4. *Lag correlation*: Pearson r of daily cyber vs. kinetic counts at −7…+7 days. It is only shown as
   meaningful with ≥10 events of each kind.
5. *Convergence days*: both series above their trailing 14-day mean + 1.5σ.

Scores are triage aids for analysts, not attribution. Co-occurrence is not causation.

## Curating content

Everything an analyst maintains lives in `backend/data/curation/*.yaml` and is applied idempotently
by `python -m app.cli init`, which the worker also runs on start.

```yaml
# groups.yaml
- match: Sandworm Team          # MITRE name or alias; unknown names create a curated-only group
  motivation: destructive
  summary: GRU's most destructive unit …
  states:
    - {country: RU, relation: operated_by, agency: "GRU Unit 74455", confidence: confirmed,
       source_name: "US DOJ indictment, 19 Oct 2020", source_url: "https://…"}
  relations:
    - {target: APT28, type: same_agency, description: "Both GRU units", confidence: confirmed}
  history:
    - {date: 2015-12-23, title: "Ukrainian power grid attack", kind: operation}
```

```yaml
# conflicts.yaml
- slug: russia-ukraine-war
  status: active
  start: 2022-02-24
  theatre: [UA, RU]
  parties: [{name: Russia, countries: [RU, BY]}, {name: Ukraine, countries: [UA]}]
  cyber_events:   [{key: viasat, date: 2022-02-24, title: "…", attributed: [RU], effect: disruptive}]
  kinetic_events: [{key: invasion, date: 2022-02-24, title: "…", country: UA, lat: 50.45, lon: 30.52}]
  links:          [{cyber: viasat, kinetic: invasion, rationale: "…"}]
```

Shipped conflicts: Russia–Ukraine war (active), Israel–Hamas & regional escalation (active),
Israel–Iran war June 2025, Crimea/Donbas 2014–2022, Russo-Georgian war 2008.

## Security notes

* Sessions are a signed JWT in an `HttpOnly`, `SameSite=Lax` cookie. Set `ST_COOKIE_SECURE=true`
  behind HTTPS. Mutating requests also require `X-Requested-With: shadowtrace` and a JSON body, which
  blocks cross-site form posts.
* Passwords are hashed with bcrypt (cost 12); auth endpoints are rate-limited per IP; login does not
  reveal whether an email exists.
* The web container sends a strict CSP. All scripts and map data are self-hosted, so the browser
  makes no third-party requests.
* Report text from feeds is rendered as text, never HTML.
* Registration can be disabled with `ST_ALLOW_REGISTRATION=false`.

## Limitations / roadmap

* Feed reports are dated by publication, which lags the actual activity. The correlator down-weights
  these, but curated activity dates remain more reliable.
* GDELT is noisy (e.g. mis-geocoding). Prefer ACLED for analysis when you have access.
* Schema migrations use `create_all` (additive). Add Alembic before changing existing columns.
* Possible next steps: an in-app curation editor for admins, e-mail/webhook alerts for favourites,
  STIX/TAXII export, MISP connector.
