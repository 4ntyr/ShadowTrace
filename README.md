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

## Quick start (local, Docker)

Requires Docker Engine 24+ with Compose v2.24+.

```bash
cp .env.example .env
```

Fill in `ST_SECRET_KEY` and `POSTGRES_PASSWORD` in `.env`. Generate each with
`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. The app refuses to start with a
weak secret. Then:

```bash
docker compose up -d --build
```

Open <http://localhost:8080> (bound to 127.0.0.1 only). On first start the worker applies database
migrations, loads the bundled MITRE ATT&CK snapshot and the curation files, backfills 24 h of GDELT
events and polls all feeds. RSS feeds only expose their latest items, so the dashboard fills up over
the first days.

## Deploying to a server

The production override adds [Caddy](https://caddyserver.com) in front of the stack. It obtains and
renews Let's Encrypt certificates automatically, redirects HTTP to HTTPS and sets HSTS. Only ports
80 and 443 are exposed; the database, API and web containers stay on the internal Docker network.

1. **Server:** any Linux host with Docker Engine 24+ and Compose v2.24+ (2 GB RAM is plenty). Open
   ports 80 and 443 (e.g. `ufw allow 80,443/tcp`) and point a DNS A/AAAA record for your domain at it.
2. **Get the code and configure:**
   ```bash
   git clone https://github.com/4ntyr/ShadowTrace.git /opt/shadowtrace
   ```
   ```bash
   cd /opt/shadowtrace && cp .env.example .env && chmod 600 .env
   ```
   In `.env`, set `ST_SECRET_KEY` and `POSTGRES_PASSWORD`, uncomment `COMPOSE_FILE=…` and set
   `ST_DOMAIN=your.domain`. Add the OTX/ACLED keys if you have them.
3. **Start:**
   ```bash
   docker compose up -d --build
   ```
   The site is live at `https://your.domain` once Caddy has fetched the certificate (a few seconds).
4. **Accounts:** for a private instance set `ST_ALLOW_REGISTRATION=false` (the UI then hides sign-up)
   and create users on the server:
   ```bash
   docker compose exec api python -m app.cli create-user analyst@example.org "Analyst Name"
   ```
   Forgotten passwords are reset with `python -m app.cli reset-password <email>`, which also signs
   out all of that user's sessions.
5. **Backups:** `deploy/backup.sh` writes a compressed `pg_dump` to `backups/` and keeps 14 days.
   Schedule it with cron:
   ```
   17 3 * * * cd /opt/shadowtrace && ./deploy/backup.sh >> backups/backup.log 2>&1
   ```
   Copy `backups/` off the server as well. To restore a dump:
   ```bash
   docker compose exec -T db pg_restore -U shadowtrace -d shadowtrace --clean --if-exists < backups/<file>.dump
   ```
6. **Updating:**
   ```bash
   git pull && docker compose up -d --build
   ```
   Database migrations run automatically on start.
7. **Monitoring:** `docker compose ps` shows container health; the in-app *Data sources* page shows
   each feed's last success and error. Logs: `docker compose logs -f worker` (rotated at 5×10 MB).

## Local development

Requirements: Python 3.12+, Node 20+, PostgreSQL 14+ (SQLite works for quick experiments).

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export ST_DATABASE_URL=postgresql+psycopg://shadowtrace:shadowtrace@localhost:5432/shadowtrace
export ST_DEBUG=true             # allows the default dev secret; never set on a server
python -m app.cli init           # migrations + MITRE snapshot + curation
python -m app.cli run rss        # or: otx | gdelt | acled | correlate | mitre
uvicorn app.main:app --reload    # API on :8000
python -m app.worker             # (separate shell) scheduler for all feeds
pytest -q                        # SQLite by default; set ST_TEST_DATABASE_URL for Postgres
alembic revision --autogenerate -m "..."   # after changing app/models.py
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
| `backend/migrations/` | Alembic migrations, applied automatically at startup |
| `deploy/` | Caddyfile (HTTPS) and the backup script |
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
configured" and is skipped; nothing breaks. Some publishers occasionally block automated readers
(e.g. BleepingComputer, CISA return 403 from some networks); those sources show as failing while the
rest keep working. Adjust the list in `backend/data/curation/feeds.yaml`. The ACLED connector targets ACLED's current OAuth API
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

* Sessions are a signed JWT in an `HttpOnly`, `SameSite=Lax` cookie, marked `Secure` automatically
  in the production setup. Changing or resetting a password signs out every other session.
* Mutating requests require `X-Requested-With: shadowtrace` and a JSON body, which blocks
  cross-site form posts.
* Passwords are hashed with bcrypt (cost 12). Auth endpoints are rate-limited per client IP (the real
  IP is passed through Caddy and nginx). Login does not reveal whether an email exists. Deleting an
  account requires the password.
* The app refuses to start with a missing or short `ST_SECRET_KEY` unless `ST_DEBUG=true`.
* nginx sends a strict CSP and Caddy adds HSTS. All scripts and map data are self-hosted, so the
  browser makes no third-party requests. Report text from feeds is rendered as text, never HTML.
* Containers run as non-root (backend); the API has no public docs endpoints.

## Limitations / roadmap

* Feed reports are dated by publication, which lags the actual activity. The correlator down-weights
  these, but curated activity dates remain more reliable.
* GDELT is noisy (e.g. mis-geocoding). Prefer ACLED for analysis when you have access.
* The ACLED connector has not yet been run against a live account.
* Possible later additions: an in-app curation editor, alerts for favourites, STIX/MISP export.
