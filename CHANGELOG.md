# Changelog — Aurora UNS Simulator

All notable changes to this project are documented here.
Format: [Semantic Versioning](https://semver.org/) — newest first.

---

## [Unreleased] — AI Layer (upcoming)

Planned work to wire the live simulator into an AI reasoning layer:
- MCP server wrapping `/api/status`, `/api/predemo`, `/api/scenario/*`
- LLM-accessible tool: `aurora_query(topic)`, `aurora_set_scenario(id)`, `aurora_trigger_dpp()`
- Context injection: live MQTT stream summaries, TerminusDB PlantState, Grafana anomalies
- Demo agent: auto-narrate fault scenarios, answer "why is OEE dropping?" from live data

---

## [0.5.0] — 2026-04-21 — Pre-Demo Health Check + TerminusDB Integration

### Added
- **`GET /api/predemo`** — atomic pre-demo readiness check that:
  - Verifies simulator is running and MQTT is connected
  - Pings TerminusDB for active `PlantState` document
  - Pings Grafana `/api/health` for database status
  - Resets active scenario to `normal`
  - Returns `{ ready: bool, checks: { simulator, terminusdb, grafana, reset } }`
- **Pre-Demo Setup panel** in `aurora.html` — idle hint → spinner → per-system green/red badge cards → overall "Ready for Demo" banner (Alpine.js `runPreDemo()` method)
- **TerminusDB env vars** added to `ecs/task-definition-aurora.json`:
  - `TERMINUS_URL = https://terminusdb.iotdemozone.com`
  - `TERMINUS_USER = admin`, `TERMINUS_TEAM = admin`, `TERMINUS_DB = aurora`
  - `TERMINUS_PASS` injected from Secrets Manager `aurora-simulator/terminus-pass-XaWHFN`

### Fixed
- **MQTT `mqtt=False` bug** — ECS was injecting an empty string for `MQTT_PASS` from Secrets Manager (overriding the hardcoded fallback). Fixed in `aurora_simulator.py` by parsing the env value and falling back to the working credential when the secret is empty or a JSON object without a recognised key.

### Infrastructure
- ECS task definition bumped from `:16` → `:17` (MQTT fix) → `:18` (TerminusDB)
- All changes committed and pushed to `main`

### Commits
| Hash | Message |
|------|---------|
| `b3caf92` | feat: add TerminusDB env vars to ECS task definition |
| `4870f5e` | fix: MQTT_PASS fallback when Secrets Manager returns empty/JSON |
| `989bbc5` | feat: add /api/predemo endpoint to aurora_simulator.py |
| `a2a9cff` | feat: add /api/predemo endpoint + Pre-Demo Setup panel in aurora.html |

---

## [0.4.0] — 2026-04-20 — TerminusDB ScenarioEvent Sync

### Added
- **TerminusDB sync** on every scenario change:
  - Creates a `ScenarioEvent` document (activated_at, triggered_by)
  - Closes the previous open event (deactivated_at, duration_s)
  - Updates `PlantState/aurora` singleton with active scenario + MQTT status
- Seed script to initialise TerminusDB schema (`FaultScenario`, `ScenarioEvent`, `PlantState`)
- Grafana panels querying TerminusDB for scenario history
- `TERMINUSDB_DESIGN.md` — architecture, schema, query patterns

### Fixed
- Background terminus task GC'd before completion — added strong reference
- HTTP calls blocking the event loop — moved to `run_in_executor`

### Commits
| Hash | Message |
|------|---------|
| `27fe9d3` | fix: keep strong ref to terminus background task to prevent GC |
| `50d14a6` | fix: run TerminusDB HTTP calls in executor thread + add debug logging |
| `7e6475f` | feat: add TerminusDB ScenarioEvent sync to simulator.py |
| `f166327` | feat: TerminusDB integration — seed script, Grafana panels, docs |

---

## [0.3.0] — 2026-04-18 — Aurora FastAPI Simulator

### Added
- **`aurora_simulator.py`** — standalone FastAPI server (port 8081) mirroring `simulator.py` pattern
- **`aurora_model.py`** — 111 MQTT streams across 15+ assets: robots, presses, ovens, sprayers, conveyors, cells, compressors
- **15 fault scenarios** with structured AI hints for demo narration
- **`aurora.html`** — full single-page operator dashboard (Alpine.js + Tailwind):
  - Live stream table with value + publish count
  - Scenario selector panel with AI hint display
  - Batch lifecycle tracker (stage, progress %, FPY, units)
  - DPP trigger button + history table
  - WebSocket real-time updates
- **`/api/batch_status`** — live batch lifecycle endpoint
- **`/api/trigger_dpp`** — manual DPP trigger with rich passport payload
- **`/api/dpp_history`** — last 10 DPP events
- **`/api/scenario/{id}`** — activate fault scenario
- **`/api/start`**, **`/api/stop`**, **`/api/reset`** — simulator control
- **InfluxDB writer** — line protocol write for all 111 streams with measurement taxonomy:
  `aurora_telemetry`, `aurora_power`, `aurora_energy`, `aurora_health`, `aurora_performance`,
  `aurora_quality`, `aurora_alarms`, `aurora_erp`, `aurora_mes`, `aurora_plant`,
  `aurora_analytics`, `aurora_dpp`, `aurora_rfid`
- **`Dockerfile.aurora`** — multi-stage build, non-root user, HEALTHCHECK
- **`deploy-aurora.sh`** — full CI/CD: zip → S3 → CodeBuild → ECR → ECS task def → ECS service update → health wait
- **`AURORA_MASTER_DEMO_GUIDE.md`** — 5-layer architecture, all 15 scenarios, exec/tech/deep-dive flows

### Infrastructure
- ECR repository: `881490131520.dkr.ecr.eu-central-1.amazonaws.com/aurora-simulator`
- ECS cluster: `pipeline-monitor`, service: `aurora-simulator`
- ALB → HTTPS: `https://aurora-api.iotdemozone.com`
- CloudWatch log group: `/ecs/aurora-simulator`
- Secrets Manager: `aurora-simulator/api-key-*`, `aurora-simulator/terminus-pass-*`

---

## [0.2.0] — 2026-04-10 — IoTAuto Base Simulator

### Added
- Original `simulator.py` — FastAPI server for IoTAuto demo fleet
- MQTT streams for welding robots, assembly cells, AGVs
- Scenario injection via `POST /api/scenario/{id}`
- WebSocket broadcast of all published events
- `static/index.html` — base operator UI

---

## [0.1.0] — 2026-03-15 — Initial Scaffold

### Added
- Project structure, `.gitignore`, `requirements*.txt`
- Basic MQTT publisher (`src/main.py`)
- Configuration via `.env`
