# Plantasaurus

Track the plants in your house and garden: what you have, where each one lives, how it has been moved and cared for, and how well it did, so you know what to buy again and where to put it.

## Concepts

| Term | Meaning |
| --- | --- |
| **Plant** | A "master" entry for a species or cultivar (e.g. *Monstera deliciosa*). Can be imported from [Open Plantbook](https://open.plantbook.io), including care ranges and an image. |
| **Instance** ("My plants") | One physical plant, or a group of identical ones, that you own. It belongs to a Plant and has a full history. |
| **Area → Spot → Position** | The location hierarchy, e.g. *Back Garden → Flowerbed → 3* or *Living Room → Windowsill → 1*. Areas are indoor, outdoor, greenhouse or covered. Spots record traits: aspect, sun exposure, near a window, heat source or draught, humidity, container, and soil. Positions are optional. |
| **Placement** | A period of time an instance spent in a spot or position. Placements are created and closed automatically when you move, transplant, retire or revive a plant. |
| **Event** | An append-only timeline entry. **Lifecycle** events (planted, moved, transplanted, repotted, died, removed, given away, revived, propagated) come from the instance actions and can't be deleted. **Care and observation** events (watered, fed, pruned, pest/disease, treated, flowered, fruited, harvested, note, photo) can be logged and removed freely. |
| **Assessment** | Ratings out of 5 (overall, health, vigour, flowering), plus "would you buy again?" and "is this a good location?". Each one is tied to the placement the plant was in at the time. |
| **Insights** | Per-plant survival rate, average lifespan, ratings and a buy-again verdict, broken down by spot, environment, aspect and sun exposure. Per-spot history shows what has grown there and how it did. |
| **Custom fields** | Admin-defined extra fields on plants, instances, areas and spots (text, number, yes/no, date, choice). |

## Running with Docker

```bash
cp .env.example .env        # optional; integrations can also be set up in the UI
docker compose up -d --build
```

Open http://localhost:8000 and create the first admin account. Data (the SQLite database and images) lives in the `plantasaurus-data` volume, mounted at `/data`.

### Open Plantbook

1. Sign up at https://open.plantbook.io.
2. Create API credentials (a client ID and secret).
3. In Plantasaurus, go to **Settings → Integrations → Open Plantbook** (admins only), enter them and click **Test & save**. The credentials are checked with Open Plantbook before they are saved.

You can set them in `.env` instead. Credentials saved in the UI take precedence:

```
PLANTASAURUS_OPB_CLIENT_ID=...
PLANTASAURUS_OPB_CLIENT_SECRET=...
```

Without credentials you can still add plants manually.

### Home Assistant devices

Spots can be linked to one **irrigation zone** and one **plant monitor** from Home Assistant. Plantasaurus finds them by device label:

1. In Home Assistant, add the label `Irrigation Zone` to each irrigation zone device and `plant` to each plant monitor device. You can change these names in Plantasaurus.
2. In Plantasaurus, go to **Settings → Integrations → Home Assistant**. Enter your HA URL and a long-lived access token (HA profile → Security). The token must belong to an administrator, because devices are read through HA's template API.
3. Edit a spot and pick its devices. The irrigation zone picker appears for non-indoor spots. A zone can water several spots, but each plant monitor can only belong to one spot.

Plantasaurus re-checks HA every 15 minutes, and whenever you open a device picker or click **Check devices now**. If an assigned device has been deleted from HA, or has lost its label, the spot is flagged. The flag shows on the dashboard, on the Locations page (with a count in the menu) and on the spot itself, and Plantasaurus raises a Home Assistant notification too (you can turn this off). If HA can't be reached, nothing is flagged; the error is shown in Settings instead.

### Configuration

All settings are environment variables with the `PLANTASAURUS_` prefix:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATA_DIR` | `/data` (container) / `./data` | Database and media location |
| `SECRET_KEY` | generated into `DATA_DIR/.secret_key` | Signs session cookies |
| `OPB_CLIENT_ID`, `OPB_CLIENT_SECRET` | unset | Open Plantbook credentials (credentials saved in the UI take precedence) |
| `COOKIE_SECURE` | `false` | Set to `true` when served over HTTPS |
| `SESSION_MAX_AGE_DAYS` | `30` | Login session length |
| `INGRESS_MODE` | `false` | Trust Home Assistant ingress user headers (see below) |
| `HA_URL`, `HA_TOKEN` | unset | Home Assistant connection (settings saved in the UI take precedence) |
| `HA_SYNC_INTERVAL_SECONDS` | `900` | How often to check that assigned HA devices still exist (`0` disables) |

## API

Everything the UI does goes through a REST API under `/api/v1`. It is documented at `/api/docs` (Swagger UI) and `/api/openapi.json`.

**Authentication** works in either of two ways:
- A session cookie, from `POST /api/v1/auth/login`.
- An API token: create one under **Settings → API tokens** and send `Authorization: Bearer pts_…`. Use this for Home Assistant, MCP, and scripts.

**Main resources:** `plants`, `areas`, `spots`, `positions`, `instances`, `events`, `assessments`, `media`, `custom-fields`, `users`, `tokens`. Each supports list, get, create, PATCH and delete.

**Instance actions** keep the placement history consistent:

```
POST /api/v1/instances                      # create (optionally placed)
POST /api/v1/instances/{id}/move
POST /api/v1/instances/{id}/transplant
POST /api/v1/instances/{id}/repot
POST /api/v1/instances/{id}/assess
POST /api/v1/instances/{id}/retire          # dead | removed | given_away (+ optional final assessment)
POST /api/v1/instances/{id}/revive
POST /api/v1/instances/{id}/propagate       # creates a child instance
GET  /api/v1/instances/{id}/timeline
GET  /api/v1/locations/tree
GET  /api/v1/plants/{id}/insights
GET  /api/v1/spots/{id}/insights
GET  /api/v1/insights/summary
GET  /api/v1/openplantbook/search?q=…
GET  /api/v1/homeassistant/status
PUT  /api/v1/homeassistant/config           # admin; tested before saving
POST /api/v1/homeassistant/sync
GET  /api/v1/homeassistant/devices?role=irrigation_zone|plant_monitor
GET  /api/v1/homeassistant/issues            # spots whose assigned device is gone
POST /api/v1/plants/import-opb
```

Example:

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/instances?status=active
```

## Home Assistant ingress readiness

Some groundwork for the future Home Assistant add-on is already in place:
- The SPA is built with relative asset paths.
- The server injects `<base href>` and `window.__BASE_PATH__` from the `X-Ingress-Path` header, so the app works under `/api/hassio_ingress/<token>/`.
- With `PLANTASAURUS_INGRESS_MODE=true`, requests from the supervisor (172.30.32.2) carrying `X-Remote-User-Id` are signed in automatically, and users are created on first sight.

## Development

```
backend/    FastAPI + SQLAlchemy 2 + Alembic (Python 3.12, managed with uv)
frontend/   React 18 + Vite + TypeScript + Mantine + TanStack Query
```

### Backend

```bash
cd backend
uv sync
uv run pytest
PLANTASAURUS_DATA_DIR=./data uv run uvicorn app.asgi:app --reload
```

Migrations run automatically on startup. After changing models, create a new migration:

```bash
uv run alembic revision --autogenerate -m "describe change"
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to :8000
```

The frontend's API types are generated from the backend's OpenAPI spec. After changing API schemas, regenerate them:

```bash
cd backend && uv run python scripts/export_openapi.py ../frontend/openapi.json
cd ../frontend && npm run gen:api
```
