# Lighthouse

**A self-hostable, ethically-scoped OSINT (open-source intelligence) investigation platform.**

Lighthouse turns scattered, *publicly available* signals — DNS, certificate transparency, WHOIS/RDAP, IP geolocation, breach exposure, public profiles, company filings — into a single, cited, navigable investigation graph. You seed a case with a domain, IP, email, username, phone number, or organization; Lighthouse runs purpose-built collectors against **official APIs and public records only**, normalizes and de-duplicates the findings into entities and relationships, scores each finding's confidence, and streams the growing graph to your browser live. Every node and edge carries provenance, so any conclusion can be traced back to its source and exported into a defensible, cited report.

> ⚖️ **For lawful, ethical use only.** Lighthouse aggregates information that is already public. It is built for security research, due diligence, brand protection, journalism, and **authorized** investigations. It is **not** a tool for harassment, stalking, unauthorized access, or bulk personal-data harvesting. The operator is responsible for ensuring they are authorized for every investigation. See [Ethics & Acceptable-Use Policy](#4-ethics--acceptable-use-policy).

### Features

- **Entity graph** — findings become a typed, directed graph (15 entity types, 12 relationship types) stored in PostgreSQL; explore it visually with an interactive Cytoscape canvas.
- **Investigation timeline** — a chronological view of what was discovered and when.
- **Asynchronous collection via Celery** — collectors run as background jobs (single-collector or seed-and-expand BFS) so the UI never blocks.
- **Live WebSocket updates** — job progress and graph deltas are pushed to the browser in real time via Redis pub/sub.
- **BYOK keyed modules** — premium sources (Shodan, Have I Been Pwned, OpenCorporates) use *your* API keys, stored Fernet-encrypted at rest.
- **Defensible, cited reports** — every entity and edge has provenance; export the case as a cited HTML/PDF report or CSV.
- **Confidence scoring** — each finding is scored 0–100 from source reliability, corroboration across independent sources, and distance from the seed.
- **RBAC** — system and per-case roles (admin / analyst / viewer) enforced on every endpoint and on the WebSocket.
- **Audit trail** — an append-only log records case creation (with AUP acknowledgment), collection runs, key operations, and membership changes.

---

## Table of Contents

1. [Architecture](#1-architecture)
2. [Tech stack](#2-tech-stack)
3. [Quick start](#3-quick-start)
4. [Ethics & Acceptable-Use Policy](#4-ethics--acceptable-use-policy)
5. [Supported modules (collectors)](#5-supported-modules-collectors)
6. [BYOK (Bring Your Own Key) setup](#6-byok-bring-your-own-key-setup)
7. [Configuration](#7-configuration)
8. [Development](#8-development)
9. [Project structure](#9-project-structure)
10. [License / disclaimer](#10-license--disclaimer)

---

## 1. Architecture

Lighthouse is a **monorepo** with three workspaces:

| Workspace | Path | What it is |
| --- | --- | --- |
| **Web** | `apps/web` | Next.js 14 (App Router) frontend. Renders the graph, timeline, entity tables, settings, and reports. Proxies all `/api/*` calls to the backend (same-origin, so the refresh cookie stays same-site). |
| **API** | `apps/api` | FastAPI backend + Celery workers. Owns auth/RBAC, the collector registry, the collection pipeline, persistence, reports, and the WebSocket. |
| **Shared types** | `packages/shared-types` | A single canonical contract file (`schema/contracts.json`) generates both the TypeScript types (`ts/`) and the Python `lighthouse_shared` package (`python/`). Enums like `EntityType`, `RelationshipType`, `Role`, and `KeyService` are defined **once** and consumed by both sides. |

### Services

`docker compose` brings up seven services:

| Service | Image / build | Role |
| --- | --- | --- |
| `postgres` | `postgres:16-alpine` | System of record **and** graph store (entities + edges tables). |
| `redis` | `redis:7-alpine` | Cache, rate-limit token buckets, Celery broker/result backend, and WebSocket pub/sub. |
| `migrate` | `apps/api` | One-shot: runs `alembic upgrade head`, then exits. App services wait for it. |
| `api` | `apps/api` | Uvicorn / FastAPI HTTP + WebSocket server (port 8000). |
| `worker` | `apps/api` | Celery worker that executes collection jobs (`--concurrency=4`). |
| `beat` | `apps/api` | Celery beat scheduler (drives optional periodic re-scans). |
| `web` | `apps/web` | Next.js server (port 3000). |

> **No separate graph database.** PostgreSQL is both the system of record and the graph store: `entities` and `edges` are ordinary relational tables (with JSONB attributes, full-text search, and confidence/provenance columns). **Redis** is purely operational — cache, rate-limit buckets, the Celery broker, and the pub/sub bus for live updates. WebSocket fan-out is decoupled from collection: workers `PUBLISH` events to a per-case Redis channel, and the API process (where the sockets live) subscribes and relays them.

### Data flow

```
┌─────────┐   /api/* (proxied)   ┌──────────────┐        ┌────────────┐
│ Browser │ ───────────────────► │   Next.js    │ ─────► │  FastAPI   │
│ (React) │ ◄─── WebSocket ───── │  (apps/web)  │        │ (apps/api) │
└─────────┘                      └──────────────┘        └─────┬──────┘
     ▲                                                         │
     │  live graph deltas                          ┌───────────┴───────────┐
     │  + job progress                             ▼                       ▼
     │                                       ┌──────────┐           ┌────────────┐
     │                                       │ Postgres │           │   Redis    │
     │                                       │ entities │           │ cache /    │
     │                                       │ + edges  │           │ buckets /  │
     │                                       └──────────┘           │ broker /   │
     │                                                              │ pub-sub    │
     │                                                              └─────┬──────┘
     │   ws:case:{id} pub/sub  ◄──────────────────────────────────────── │
     │                                                                    │
     └───────────────────────────────────────────────────────┐          │
                                                               │          ▼
                                           ┌──────────────────────────────────────┐
   Collection (async):                     │        Celery worker (apps/api)        │
   API enqueues a job  ───────────────────►│                                        │
                                           │  1. ScopeGuard   (refuse out-of-scope) │
                                           │  2. Circuit breaker (skip flaky source)│
                                           │  3. Key check    (graceful skip / BYOK)│
                                           │  4. Rate limit   (Redis token bucket)  │
                                           │  5. Cache        (per-source TTL)      │
                                           │  6. httpx + tenacity (outbound fetch)  │
                                           │  7. Pipeline: normalize → dedupe →     │
                                           │     score → enrich                     │
                                           │  8. Persist entities/edges + provenance│
                                           │  9. Publish graph delta → WS push      │
                                           │ 10. Write audit entry                  │
                                           └──────────────────────────────────────┘
```

A **collector** is (close to) a pure function: it receives a target and a context, makes outbound requests, and returns *drafts* — `(type, value)` tuples with attributes and provenance. It never persists, dedupes, or scores; the pipeline does that. This separation is what makes collectors trivially testable with `respx` and plain assertions.

The **pipeline** (`apps/api/app/pipeline/`):

- **normalize** — canonicalizes selectors so the same real-world thing always dedupes to one entity (`Example.COM.` → `example.com`; IDNs → punycode; phone numbers → E.164) and may even correct an entity's *type* (a domain with a path becomes a subdomain/URL).
- **dedupe / persist** — idempotent upserts on natural keys; re-running a collector never duplicates anything. Provenance is updated in place per `(target, collector, source_url)`, and `source_count` tracks the number of *distinct* collectors that cited a thing.
- **score** — confidence (0–100) from three forces: per-collector base reliability, a corroboration boost when independent sources agree, and a decay with graph distance from the seed.
- **enrich** — merges attributes from multiple sources and flags entities as `conflicting` when sources disagree.

---

## 2. Tech stack

| Layer | Technology |
| --- | --- |
| **Frontend** | Next.js 14 (App Router) · React 18 · TypeScript 5 · TanStack Query · Zustand · Tailwind CSS · Radix UI · Cytoscape (+ fcose) · Recharts · Framer Motion · lucide-react · sonner |
| **Backend** | Python · FastAPI · Uvicorn · Pydantic v2 / pydantic-settings |
| **Async / jobs** | Celery 5 (worker + beat) with Redis broker & result backend |
| **Database** | PostgreSQL 16 · SQLAlchemy 2 (async, asyncpg) · Alembic (psycopg sync) |
| **Cache / bus** | Redis 7 (cache, token buckets, Celery broker, WebSocket pub/sub) |
| **HTTP / resilience** | httpx · tenacity (retries) · per-service circuit breaker |
| **Security** | Argon2 password hashing · PyJWT (access/refresh) · pyotp (TOTP 2FA) · `cryptography` Fernet (BYOK keys at rest) |
| **OSINT libraries** | dnspython · tldextract · idna · phonenumbers |
| **Reports** | WeasyPrint (PDF) · Jinja2 (HTML) · CSV |
| **Testing** | Backend: pytest · pytest-asyncio · respx · fakeredis · freezegun · ruff. Frontend: Vitest · Testing Library · Playwright (e2e) |

---

## 3. Quick start

### Prerequisites

- **Docker** and **Docker Compose** (v2 / `docker compose`).

That is the only requirement to run the full stack — every other dependency is built into the images.

### Steps

1. **Copy the env template:**

   ```bash
   cp .env.example .env
   ```

2. **Generate strong secrets** and put them in `.env`. Both are **required** — the app refuses to boot without them.

   ```bash
   # SECRET_KEY — signs JWT access & refresh tokens
   python -c "import secrets; print(secrets.token_urlsafe(64))"

   # FERNET_KEY — encrypts BYOK API keys at rest (must be a valid Fernet key)
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Paste the outputs into `SECRET_KEY=` and `FERNET_KEY=` in `.env`. In **production**, Lighthouse will refuse to start if `SECRET_KEY` is still the insecure dev default, is shorter than 32 chars, or if `BOOTSTRAP_ADMIN_PASSWORD` is still the example value.

3. **Bring up the stack:**

   ```bash
   docker compose up --build
   ```

   Database **migrations run automatically** via the one-shot `migrate` service before the API, worker, and beat start.

4. **Open the app:**

   - Web UI → **http://localhost:3000**
   - API docs (Swagger) → **http://localhost:8000/api/docs** (ReDoc at `/api/redoc`)

5. **Create your account.** The **first registered account becomes the admin.** (Alternatively, you can pre-seed an admin via the optional `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` env vars, applied on first startup when no users exist.)

---

## 4. Ethics & Acceptable-Use Policy

Ethics is a core product value of Lighthouse, not a footnote. The following is both the policy **and** a description of how that policy is enforced in code.

### Acceptable use

Lighthouse is for **lawful, ethical intelligence work only**, including:

- security research and attack-surface mapping of assets you are authorized to assess,
- corporate due diligence and third-party / vendor risk review,
- brand protection and anti-phishing/typosquat investigations,
- journalism and public-interest research,
- other **authorized** investigations.

Lighthouse **only aggregates publicly available information** retrieved from official APIs and public records.

### Prohibited use

Lighthouse must **not** be used for:

- harassment, stalking, doxxing, or intimidation of any person,
- unauthorized access, credential stuffing, password cracking, or any attempt to bypass authentication,
- exploitation, scanning, or probing of systems you are not authorized to test,
- scraping login-gated, paywalled, or otherwise private content,
- bulk harvesting of personal data beyond the legitimate scope of a specific, authorized investigation.

**You, the operator, are solely responsible for ensuring you are legally authorized to conduct each investigation** and for complying with all applicable laws and each data source's Terms of Service.

### How the guardrails are enforced in code (not just policy)

Lighthouse encodes its ethics into the system so the policy isn't merely aspirational:

1. **Blocking acknowledgment gate on case creation.** Every case requires a stated **legal basis** and explicit **AUP acceptance** before it can be created. The acknowledgment (legal basis, AUP version, timestamp) is recorded in the **immutable audit log** as part of case creation — there is no investigation without an accountable, logged acknowledgment.

2. **The `ScopeGuard` (SSRF & out-of-scope protection).** Before any collector runs, and before any individual outbound request, the target/host is checked:
   - **Private, loopback, link-local, reserved, multicast, and unspecified IPs are always refused** — this prevents internal-network scanning and SSRF.
   - Hosts on the configured **denylist** (exact match, `*.suffix` wildcards, or CIDR ranges) are refused. The default denylist includes `localhost`, `127.0.0.1`, and **`*.gov` / `*.mil`**.
   - Non-`http(s)` URL schemes are refused outright.
   - Out-of-scope targets are recorded as **skipped** (with the reason) in the audit log — never silently dropped.

3. **Public sources only, by design.** Every collector documents that it uses only publicly accessible data / official APIs, and each one honors its source's ToS and rate limits. There are no collectors that authenticate to, or scrape, private/login-gated content.

4. **Minimized, non-sensitive findings for people-related lookups.** The username and email checks report only **existence** and **breach NAMES** — never passwords, hashes, or any breached content:
   - The HIBP breach collector explicitly requests `truncateResponse=true`, so the API returns *which* breaches an email appeared in — and nothing inside them.
   - The username search reports only that a **public profile URL returns HTTP 200**; it never authenticates or reads private data.

5. **Good network citizenship.** Every outbound request is **rate-limited** with a distributed Redis token bucket (atomic across all API processes and workers, so a source's budget is never over-spent), **cached** with a per-source TTL, and sent with an identifying `User-Agent` so sources can identify and contact the operator. A **per-service circuit breaker** stops hammering a struggling or blocking source. The HTTP fingerprint collector additionally honors `robots.txt`.

6. **RBAC everywhere.** System-wide and per-case roles (admin / analyst / viewer) are enforced on **every** REST endpoint and on the **WebSocket** handshake. Viewers cannot create cases or run collections; case access is gated by ownership/membership.

7. **Full audit trail.** An append-only audit log records case creation (with the AUP acknowledgment), every collection run and its outcome, key create/test/delete operations, membership changes, and more — exportable for accountability.

---

## 5. Supported modules (collectors)

Lighthouse ships **14 collectors**. They are auto-discovered at runtime, and the UI renders the available modules dynamically (including "add key to enable" states). `*` marks a **keyed** module that requires a BYOK API key.

| Module | Accepts | Produces | Cost | Data source |
| --- | --- | --- | --- | --- |
| `dns_records` | domain, subdomain | ip, domain, subdomain | free | Public recursive DNS |
| `reverse_dns` | ip | domain, subdomain | free | Public reverse DNS (PTR) |
| `rdap_whois` | domain, ip, asn | organization, person, email, domain | free | RDAP (modern WHOIS) via rdap.org |
| `cert_transparency` | domain | subdomain, certificate, domain | free | Certificate Transparency logs (crt.sh) |
| `ip_geo` | ip | location, organization, asn | free | IP-geolocation API (ipwho.is) |
| `http_fingerprint` | domain, subdomain, url, ip | url | free | The target's own web server |
| `email_format` | email | domain | free | Email syntax + public DNS MX |
| `username_search` | username | social_profile | free | ~30 public profile pages |
| `github_user` | username | social_profile, email, organization, url, location, username | free | Public GitHub REST API |
| `wayback` | domain, subdomain, url | url | free | Internet Archive Wayback (CDX API) |
| `phone_meta` | phone | location, organization | free | libphonenumber metadata (local, offline) |
| `shodan` `*` | ip | url, organization, location, asn, domain | keyed | Shodan host API (BYOK) |
| `email_breach` `*` | email | breach | keyed | Have I Been Pwned (BYOK) |
| `company_records` `*` | organization | organization, person, location | keyed | OpenCorporates (BYOK) |

### Free modules

- **`dns_records` — DNS Records.** Resolves A/AAAA/MX/NS/CNAME/TXT/SOA records for a domain via a public recursive resolver. Emits IPs (with `resolves_to` edges), mail/name servers, and folds TXT/SOA findings (SPF/DMARC presence) onto the seed. No zone transfers.
- **`reverse_dns` — Reverse DNS (PTR).** Resolves the PTR (reverse DNS) hostname(s) for an IP via public DNS.
- **`rdap_whois` — RDAP / WHOIS.** Looks up registration data — registrar, registrant (when not redacted for privacy), abuse/registrant contacts, registration/expiry dates, and nameservers — over the public RDAP protocol via the rdap.org bootstrap. Registration data only; no login-gated or private data.
- **`cert_transparency` — Certificate Transparency (crt.sh).** Enumerates subdomains and certificates for a domain by mining the SANs and common names recorded in publicly logged certificates. No authentication.
- **`ip_geo` — IP Geolocation.** Resolves **coarse** city/region/country, the hosting ASN, and the network operator for an IP via the free, keyless ipwho.is API. Coarse location only.
- **`http_fingerprint` — HTTP Fingerprint.** A single, polite HTTP(S) fetch of a public page that captures the title, `Server` / `X-Powered-By` headers, and lightweight technology hints. It identifies itself via the configured `User-Agent`, **honors robots.txt**, enforces the scope/SSRF guard, and never attempts to bypass authentication.
- **`email_format` — Email Deliverability (MX).** Validates email syntax and checks whether the domain publishes MX records (a deliverability *heuristic*), via public DNS only. It **never sends mail** and **never connects to an SMTP server or probes mailboxes.**
- **`username_search` — Username Search.** Checks whether a username has a public profile page across ~30 platforms (GitHub, GitLab, Reddit, Mastodon, etc.). It requests **only public profile URLs** with a plain GET, considers a profile to exist **only** when the URL returns HTTP 200, and never authenticates or reads private content. Every request passes through the scope guard.
- **`github_user` — GitHub User.** Resolves a username against the public GitHub REST API (no auth): profile, public repos, and any **publicly published** linked identities — public email (if the user published it), company, blog, location, and linked Twitter/X handle. Public profile/repos only.
- **`wayback` — Wayback Machine.** Surfaces historical snapshots of public pages under a domain/host/URL from the Internet Archive CDX API, so an analyst can see archived URLs and when they were first captured. No authentication.
- **`phone_meta` — Phone Metadata.** A **pure, local, offline** computation over the bundled libphonenumber metadata: derives region, carrier, line type, and timezones from a phone number's structure. It performs **no network lookups** and never touches private subscriber data.

### Keyed modules (BYOK — `*`)

- **`shodan` — Shodan.** Passive host intel from Shodan's *existing* scan data: network operator, ASN, coarse location, observed hostnames, and open ports/OS as attributes. **It never initiates a scan** — it only reads data Shodan already collected from public hosts. Requires your Shodan API key.
- **`email_breach` — Email Breaches (HIBP).** Checks an email against Have I Been Pwned and returns the **names** of breaches it appeared in. It requests `truncateResponse=true`, so HIBP returns breach NAMES **only** — never passwords, hashes, or breached content. Requires your HIBP API key.
- **`company_records` — Company Records (OpenCorporates).** Searches public company registries for matching companies — surfacing jurisdiction, company number, status, and registered address — and, for the top match, the officers (directors, etc.) on file. All public filing data. Requires your OpenCorporates API token.

When a keyed module has no key available, it **degrades gracefully**: the UI shows an "add key to enable" state and the job is recorded as *skipped* (with a reason) rather than failing.

---

## 6. BYOK (Bring Your Own Key) setup

Three modules call premium services using **your own API keys**. BYOK is the primary key mechanism — keys are per **user** or per **case**, not baked into the deployment.

| Service | Used by | Where to get a key |
| --- | --- | --- |
| **Shodan** | `shodan` | https://account.shodan.io (API key on your account page) |
| **Have I Been Pwned** | `email_breach` | https://haveibeenpwned.com/API/Key (paid API key) |
| **OpenCorporates** | `company_records` | https://opencorporates.com/api_accounts/new (API token) |

### How keys are stored

- Keys are encrypted **at rest** with Fernet (AES-128-CBC + HMAC) using `FERNET_KEY`.
- Plaintext is **never returned to the client** and never logged. The UI shows only a masked hint, e.g. `••••1234` (the last four characters stored alongside the ciphertext).
- Plaintext is decrypted only momentarily, server-side, to make an outbound request.

### Adding a key

1. Go to **Settings → Keys** in the web UI.
2. Add a key for a service, choosing the scope:
   - **User-scoped** — available to you across your cases.
   - **Case-scoped** — available within a specific case (case owner / admin only).
3. Use **Test** to verify the key against its upstream service. Lighthouse calls a lightweight status endpoint (Shodan `/api-info`, HIBP `/subscription/status`, OpenCorporates `/account_status`) and records validity. The masked key, validity, and last-used time are surfaced; the secret itself never leaves the server.

**Key resolution order** for a collector run is: case-scoped key → the requesting user's key → optional process-wide env fallback.

### Optional global fallback

You may set process-wide fallback keys via env so keyed collectors can run without per-user setup: `SHODAN_API_KEY`, `HIBP_API_KEY`, `OPENCORPORATES_API_KEY`. Leave them blank to force BYOK-only. If none is set and a user hasn't added a key, the keyed module simply stays disabled.

---

## 7. Configuration

A **single `.env`** (copied from `.env.example`) drives every service. Field names are the lowercased env var names. `SECRET_KEY` and `FERNET_KEY` are **required** — the app refuses to start without them, and `FERNET_KEY` is validated to be a usable Fernet key.

### Core / Auth

| Variable | Default | Description |
| --- | --- | --- |
| `LIGHTHOUSE_ENV` | `development` | `development` or `production`. In production, insecure defaults are rejected at startup. |
| `LOG_LEVEL` | `INFO` | Logging level. |
| `SECRET_KEY` | *(required)* | Signs JWT access + refresh tokens. App refuses to boot if unset; must be ≥ 32 chars in production. |
| `FERNET_KEY` | *(required)* | Fernet key used to encrypt BYOK API keys at rest. Must be a valid Fernet key. |
| `ACCESS_TOKEN_TTL_SECONDS` | `900` | Access JWT lifetime (15 min). |
| `REFRESH_TOKEN_TTL_SECONDS` | `1209600` | Rotating refresh-cookie lifetime (14 days). |
| `TOTP_ISSUER` | `Lighthouse` | Issuer label shown in authenticator apps for TOTP 2FA. |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins for the API (the Next.js app origin). |
| `MAX_LOGIN_ATTEMPTS` | `5` | Lock an account after this many consecutive failures. |
| `LOGIN_LOCKOUT_SECONDS` | `900` | Lockout window (15 min). |
| `BOOTSTRAP_ADMIN_EMAIL` | `admin@lighthouse.local` | Optional first-run admin, created on startup only if there are no users yet. |
| `BOOTSTRAP_ADMIN_PASSWORD` | `ChangeMe!2024` | Password for the bootstrap admin. Must be changed from this example in production. |

### Database

| Variable | Default | Description |
| --- | --- | --- |
| `POSTGRES_USER` | `lighthouse` | Postgres role. |
| `POSTGRES_PASSWORD` | `lighthouse` | Postgres password. |
| `POSTGRES_DB` | `lighthouse` | Database name. |
| `POSTGRES_HOST` | `postgres` | DB host (service name inside the compose network). |
| `POSTGRES_PORT` | `5432` | DB port. |
| `DATABASE_URL` | `postgresql+asyncpg://lighthouse:lighthouse@postgres:5432/lighthouse` | Async SQLAlchemy URL used by the API + worker. |
| `SYNC_DATABASE_URL` | `postgresql+psycopg://lighthouse:lighthouse@postgres:5432/lighthouse` | Sync URL used by Alembic migrations. |

### Redis / Celery

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_URL` | `redis://redis:6379/0` | Cache + rate-limit buckets + pub/sub. |
| `CELERY_BROKER_URL` | `redis://redis:6379/1` | Celery broker. |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/2` | Celery result backend. |

### Collection engine

| Variable | Default | Description |
| --- | --- | --- |
| `HTTP_USER_AGENT` | `LighthouseOSINT/1.0 (+https://github.com/your-org/lighthouse; research use)` | Sent on every outbound request so sources can identify and contact you. |
| `REQUEST_TIMEOUT_SECONDS` | `20` | Per-request timeout for outbound HTTP. |
| `DEFAULT_AUTOEXPAND_DEPTH` | `2` | Default BFS depth for seed-and-expand collection. |
| `DEFAULT_NODE_BUDGET` | `250` | Default max nodes visited during auto-expand. |
| `SCOPE_DENYLIST` | `localhost,127.0.0.1,*.gov,*.mil` | Comma-separated hosts/domains/CIDRs the `ScopeGuard` always refuses (in addition to RFC1918/reserved IPs). |
| `CIRCUIT_BREAKER_THRESHOLD` | `5` | Open a service's circuit breaker after this many consecutive failures. |
| `CIRCUIT_BREAKER_COOLDOWN_SECONDS` | `120` | Cooldown before a tripped breaker resets. |
| `REPORTS_DIR` | `/data/reports` | Where generated reports are written. |

### BYOK fallbacks (optional)

| Variable | Default | Description |
| --- | --- | --- |
| `SHODAN_API_KEY` | *(blank)* | Optional global fallback Shodan key (BYOK is primary). |
| `HIBP_API_KEY` | *(blank)* | Optional global fallback Have I Been Pwned key. |
| `OPENCORPORATES_API_KEY` | *(blank)* | Optional global fallback OpenCorporates token. |

### Frontend (Next.js)

| Variable | Default | Description |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Browser-exposed API URL. |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000` | Browser-exposed WebSocket URL. |
| `INTERNAL_API_URL` | `http://api:8000` | Server-side URL the Next.js server uses to reach the API inside the compose network (used by the `/api/*` proxy rewrite). |

---

## 8. Development

You can run pieces of the stack locally outside Docker. The simplest path is to keep `postgres` and `redis` running via Docker and run the API/worker/web from source.

### Backend

```bash
cd apps/api
pip install -r requirements-dev.txt      # includes requirements.txt + test/lint tools
PYTHONPATH=. pytest                       # run the backend test suite
ruff check .                              # lint
```

The backend ships **70+ tests** (`apps/api/tests/`) covering every collector, the `ScopeGuard`, the rate limiter, the pipeline/DB persistence, RBAC, auth, the registry, and the report renderer. Collector tests use `respx` to mock HTTP and `fakeredis` for Redis, so they need no network or live services.

Run the API and workers from source (with Postgres/Redis reachable per your `.env`):

```bash
# API
uvicorn app.main:app --reload --port 8000
# Worker
celery -A app.tasks.celery_app.celery_app worker --loglevel=INFO
# Beat (optional, for scheduled re-scans)
celery -A app.tasks.celery_app.celery_app beat --loglevel=INFO
```

### Frontend

Install workspace dependencies from the repo root, then run the dev server:

```bash
npm install            # at the repo root (npm workspaces)
npm run dev            # Next.js dev server on http://localhost:3000
npm run test           # Vitest unit tests
npm run test:e2e       # Playwright end-to-end test
```

The frontend includes **Vitest** unit tests plus a **Playwright** end-to-end test.

### Regenerate shared types

`packages/shared-types/schema/contracts.json` is the **canonical source of truth** for cross-language contracts. Edit it, then regenerate the TypeScript and Python outputs (never edit the generated files by hand):

```bash
npm run gen:types      # runs packages/shared-types/scripts/generate.mjs
```

### Database migrations (Alembic)

Migrations live in `apps/api/alembic/versions/`. In Docker they run automatically via the `migrate` service. To create or apply them manually:

```bash
cd apps/api
alembic upgrade head                       # apply
alembic revision --autogenerate -m "msg"   # create a new migration
```

Alembic uses `SYNC_DATABASE_URL`.

---

## 9. Project structure

```
.
├── apps/
│   ├── api/                         # FastAPI backend + Celery workers
│   │   ├── app/
│   │   │   ├── api/v1/              # REST + WebSocket routers
│   │   │   │   ├── auth.py          #   register/login/refresh/logout, TOTP 2FA
│   │   │   │   ├── cases.py         #   cases + the AUP acknowledgment gate
│   │   │   │   ├── entities.py      #   entities, search, graph
│   │   │   │   ├── edges.py         #   relationships
│   │   │   │   ├── jobs.py          #   run / auto-expand / retry / cancel collection
│   │   │   │   ├── modules.py       #   collector capabilities + per-case settings
│   │   │   │   ├── keys.py          #   BYOK key manager (encrypted, masked)
│   │   │   │   ├── reports.py       #   cited HTML/PDF/CSV reports
│   │   │   │   ├── audit.py         #   audit log read + export
│   │   │   │   └── ws.py            #   live case feed (WebSocket)
│   │   │   ├── collectors/          # the 14 collectors + base.py (ScopeGuard) + registry
│   │   │   ├── core/                # security, rbac, crypto, keys, ratelimit, audit, events
│   │   │   ├── pipeline/            # normalize → dedupe → score → enrich → ingest
│   │   │   ├── tasks/               # Celery app + collection tasks + scheduled re-scan
│   │   │   ├── db/                  # SQLAlchemy models (entities, edges, provenance, …)
│   │   │   ├── reports/             # WeasyPrint renderer + Jinja2 template
│   │   │   ├── schemas/             # Pydantic request/response models
│   │   │   ├── config.py            # env-driven settings (refuses insecure prod config)
│   │   │   └── main.py              # FastAPI app entrypoint
│   │   ├── alembic/                 # database migrations
│   │   ├── tests/                   # 70+ pytest tests
│   │   ├── requirements.txt
│   │   └── requirements-dev.txt
│   └── web/                         # Next.js 14 frontend
│       ├── app/                     # App Router pages (auth + app: dashboard, cases, …)
│       ├── components/              # graph, entity, timeline, report, collection, ui
│       ├── lib/                     # api client, websocket, store, types
│       ├── tests/                   # Vitest unit tests
│       └── package.json
├── packages/
│   └── shared-types/               # canonical contracts → generated TS + Python
│       ├── schema/contracts.json   #   source of truth (enums, interfaces, palette)
│       ├── ts/                      #   generated TypeScript
│       ├── python/                 #   generated lighthouse_shared package
│       └── scripts/generate.mjs    #   codegen
├── docker-compose.yml              # postgres · redis · migrate · api · worker · beat · web
├── .env.example
└── package.json                    # npm workspaces root
```

---

## 10. License / disclaimer

Lighthouse is provided **as-is, without warranty of any kind**, express or implied. It is intended exclusively for **lawful, ethical** open-source intelligence work on information that is already public, and for investigations the operator is **authorized** to conduct.

By using Lighthouse you accept sole responsibility for ensuring your use complies with all applicable laws and regulations and with the Terms of Service of every data source it queries. The authors and contributors accept no liability for misuse or for any damages arising from use of this software. See [Ethics & Acceptable-Use Policy](#4-ethics--acceptable-use-policy) for the full acceptable-use terms.
