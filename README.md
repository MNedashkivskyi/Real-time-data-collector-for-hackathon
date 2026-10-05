# Warsaw Parking Data Collector & ETL Pipeline

Automated service designed to continuously ingest, process, and persist real-time parking availability across Warsaw using the Warsaw Open Data API. Built with a containerized PostgreSQL backend and pgAdmin web monitoring interface.

---

## Architecture Overview

- **Collector Service (`vacum.py`)**: Python worker polling the municipal API every 5 minutes with resilient JSON parsing, adaptive fallback matching, and automated retry mechanisms. Creates the database schema on startup and skips malformed records individually.
- **Relational Database (`PostgreSQL 15`)**: Relational storage separated into a static registry table and an append-only time-series log table.
- **Web UI (`pgAdmin 4`)**: Integrated browser dashboard for ad-hoc SQL querying and occupancy visualization.
- **Orchestration (`Docker Compose`)**: Complete stack managed via containerized networks and persistent volumes.

---

## Quick Start (local, Docker Compose)

### 1. Prerequisites

- Docker and Docker Compose installed.

### 2. Configure Environment

Create your local environment file from the template and set `API_TOKEN`:

```bash
cp .env.example .env
```

### 3. Deploy the Stack

Spin up the entire pipeline in background mode:

```bash
docker compose up --build -d
```

To inspect collector logs:

```bash
docker compose logs -f collector
```

---

## Deploying on Railway

Railway does not run `docker-compose.yaml`. You create two services by hand: a PostgreSQL database and the collector, which builds from the existing `Dockerfile`. pgAdmin is not needed.

### 1. Push the repo to GitHub

Railway deploys from a GitHub repository.

### 2. Create the project

On [railway.com](https://railway.com) choose **New Project → Deploy from GitHub repo** and pick this repo. Railway detects the `Dockerfile` automatically. The first deploy cannot reach a database yet and will log connection retries; that is expected.

### 3. Add the database

In the project canvas choose **Create → Database → Add PostgreSQL**.

### 4. Set variables on the collector service

Open the collector service, go to **Variables → Raw Editor** and paste:

```
API_TOKEN=<your Warsaw Open Data token>
DB_HOST=${{Postgres.PGHOST}}
DB_PORT=${{Postgres.PGPORT}}
DB_NAME=${{Postgres.PGDATABASE}}
DB_USER=${{Postgres.PGUSER}}
DB_PASSWORD=${{Postgres.PGPASSWORD}}
```

`Postgres` must match the database service's name on the canvas. These references use Railway's private network, so the database needs no public exposure for the collector.

### 5. Leave the collector's networking alone

The collector is a background worker with no HTTP port. Do not generate a domain or add a healthcheck. In **Settings**, set the restart policy to **Always**.

### 6. Deploy and verify

Apply the variable changes (this triggers a redeploy), then open the collector's **Deploy Logs**. Within a few seconds you should see:

```
Starting parking data fetcher...
Database schema is ready.
Saved N parking entries to the database (0 skipped).
```

The tables are created automatically by the collector on startup. To confirm rows are arriving, copy `DATABASE_PUBLIC_URL` from the Postgres service's **Variables** tab and run:

```bash
psql "<DATABASE_PUBLIC_URL>" -c "SELECT count(*), max(recorded_at) FROM parking_occupancy_logs;"
```

You can also browse the data in the Postgres service's **Database** tab, or point a local pgAdmin at `DATABASE_PUBLIC_URL`.

### Troubleshooting

| Log message | Cause |
| --- | --- |
| `Database connection error, retrying...` repeating | The variable references in step 4 are wrong, or the database service has a different name. |
| `Error fetching parking data: ...` | The API is unreachable or rejected the request; check `API_TOKEN`. |
| `No parking list found in response: ...` | The API answered without a parking list. The message includes the response body, which usually names the problem (for example an invalid key). |
| `Skipping parking '<name>': ...` | One record was malformed and was skipped; the rest of the batch was saved. |

---

## Database Schema

The collector applies `init.sql` on startup (and Docker Compose also runs it when the database is first created). It defines two entities:

### `parkings` (Dimension Table)

- Tracks unique parking assets (`name` as primary key).
- Stores capacity, geographical coordinates (`latitude`, `longitude`), operator metadata, and address.
- Refreshes capacity and coordinates on incoming payloads via `ON CONFLICT (name) DO UPDATE`.

### `parking_occupancy_logs` (Time-Series Fact Table)

- Stores periodic measurements: `free_public`, `free_disabled`, `free_electric`, and `total_free`.
- Records timestamped occupancy changes (`recorded_at`).
- Retains full raw payload snapshot in `jsonb` format (`raw_payload`) for auditing and future schema evolution.

---

## Web UI Access (pgAdmin, local stack only)

- URL: http://localhost:5050
- Default Login: `admin@admin.com`
- Default Password: `admin`

Connecting to the database in pgAdmin:

- Host name/address: `db` (or `parking_postgres`)
- Port: `5432`
- Maintenance database: `parking_db`
- Username: `postgres`
- Password: `postgres` (or value set in `.env`)
