# Aurora UNS Simulator

Physics-based factory simulator for the **Aurora Industries Battery Case Plant** — 111 MQTT streams, 15 fault scenarios, full REST + WebSocket API, TerminusDB knowledge graph, Grafana dashboards, and pre-demo health checks.

Live: **https://aurora-api.iotdemozone.com**
UI: **https://aurora-api.iotdemozone.com/**

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    aurora-api.iotdemozone.com            │
│              (ECS Fargate  aurora-simulator:18)          │
│                                                          │
│  aurora_simulator.py  ──►  MQTT  ──►  mqtt.iotdemozone  │
│                       ──►  InfluxDB  (aurora bucket)     │
│                       ──►  TerminusDB  (aurora db)       │
│                       ──►  WebSocket  (browser clients)  │
└─────────────────────────────────────────────────────────┘
         │ REST API + WS
         ▼
  aurora.html  (Alpine.js operator dashboard)
         │
  Grafana  https://grafana.iotdemozone.com
  TerminusDB  https://terminusdb.iotdemozone.com
```

### Data layers

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **UNS / real-time** | MQTT `mqtt.iotdemozone.com:1883` | 111 streams, all assets |
| **Time-series** | InfluxDB `aurora` bucket | Sensor history, Grafana source |
| **Knowledge graph** | TerminusDB `admin/aurora` | Scenario history, PlantState, DPP lineage |
| **Operator UI** | `aurora.html` (served from FastAPI) | Live dashboard, scenario control |
| **AI layer** *(upcoming)* | MCP server + LLM | Natural language plant reasoning |

---

## API Reference

All endpoints require header `X-API-Key: <key>` except `/health`, `/`, `/api/config`.

### System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness — `{status, running, mqtt, streams, uptime}` |
| `GET` | `/api/config` | Returns `{api_key}` for UI bootstrap |
| `GET` | `/api/status` | Full simulator state — streams, scenarios, batch, recent messages |

### Simulator control

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/start` | Start all streams |
| `POST` | `/api/stop` | Stop all streams |
| `POST` | `/api/reset` | Reset counters + scenario to normal |

### Scenarios

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/scenario/{id}` | Activate fault scenario (updates TerminusDB) |

Available scenario IDs: `normal`, `robot_arm_wear`, `press_hydraulic_leak`, `oven_temperature_drift`, `conveyor_bearing_fault`, `spray_nozzle_clog`, `compressor_pressure_drop`, `batch_quality_failure`, `energy_spike`, `rfid_reader_error`, `mes_sync_delay`, `vision_system_fault`, `coolant_contamination`, `gripper_calibration_drift`, `power_factor_degradation`

### Batch / DPP

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/batch_status` | Live batch lifecycle — stage, progress %, FPY, unit counts |
| `POST` | `/api/trigger_dpp` | Fire rich DPP batch-complete passport event |
| `GET` | `/api/dpp_history` | Last 10 DPP events |

### Pre-Demo

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/predemo` | Atomic readiness check — verifies all 4 systems, resets scenario |

```json
// Example response
{
  "ready": true,
  "checks": {
    "simulator":   { "ok": true,  "detail": "running=True mqtt=True streams=111" },
    "terminusdb":  { "ok": true,  "detail": "active_scenario=normal" },
    "grafana":     { "ok": true,  "detail": "database=ok version=11.5.2" },
    "reset":       { "ok": true,  "detail": "scenario reset to normal" }
  }
}
```

### WebSocket

`wss://aurora-api.iotdemozone.com/ws?api_key=<key>`

Receives JSON frames:
- `{type: "init", ...}` — full status on connect
- `{type: "message", stream_id, label, topic, value, ts}` — every published message
- `{type: "stats", running, mqtt_connected, total_published, rate, scenario}` — every 2s
- `{type: "scenario_change", scenario, label, affected}` — on scenario switch
- `{type: "dpp_triggered", batch_id, ...}` — on DPP event
- `{type: "control", running}` — start/stop/reset

---

## Local Development

```bash
# 1. Clone & install
git clone https://github.com/joeybernal/uns-simulator.git
cd uns-simulator
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-aurora.txt

# 2. Set env
export MQTT_HOST=mqtt.iotdemozone.com
export MQTT_PASS=<password>
export AURORA_API_KEY=<key>          # optional, disables auth if unset

# 3. Run
python3 aurora_simulator.py
# → http://localhost:8081
```

---

## Deploy to AWS

```bash
bash deploy-aurora.sh
```

Pipeline: `aurora_simulator.py` + `aurora_model.py` + `static/aurora.html` + `Dockerfile.aurora`
→ **S3** zip → **CodeBuild** Docker build → **ECR** push → **ECS** task def register → service update → health wait

### Infrastructure

| Resource | Value |
|----------|-------|
| ECS Cluster | `pipeline-monitor` |
| ECS Service | `aurora-simulator` |
| Current task def | `aurora-simulator:18` |
| ECR repo | `881490131520.dkr.ecr.eu-central-1.amazonaws.com/aurora-simulator` |
| Region | `eu-central-1` |
| ALB endpoint | `https://aurora-api.iotdemozone.com` |
| CloudWatch logs | `/ecs/aurora-simulator` |

### Secrets Manager

| Secret name | Env var injected | Notes |
|-------------|-----------------|-------|
| `pipeline-monitor/mqtt-password-Vt925U` | `MQTT_PASS` | MQTT broker credential |
| `aurora-simulator/api-key-hauld3` | `AURORA_API_KEY` | REST API key |
| `aurora-simulator/terminus-pass-XaWHFN` | `TERMINUS_PASS` | TerminusDB `admin` password (JSON: `{"password":"..."}`) |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_HOST` | `mqtt.iotdemozone.com` | MQTT broker host |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USER` | `admin` | MQTT username |
| `MQTT_PASS` | *(hardcoded fallback)* | MQTT password — falls back to embedded default if secret is empty |
| `AURORA_PORT` | `8081` | FastAPI listen port |
| `AURORA_API_KEY` | *(none)* | REST API key — auth disabled if empty |
| `INFLUX_URL` | *(empty)* | InfluxDB URL — writes disabled if empty |
| `INFLUX_TOKEN` | *(empty)* | InfluxDB auth token |
| `INFLUX_ORG` | `iotauto` | InfluxDB org |
| `INFLUX_BUCKET` | `aurora` | InfluxDB bucket |
| `TERMINUS_URL` | *(empty)* | TerminusDB base URL — sync disabled if empty |
| `TERMINUS_USER` | `admin` | TerminusDB username |
| `TERMINUS_PASS` | *(empty)* | TerminusDB password — parsed from JSON if needed |
| `TERMINUS_TEAM` | `admin` | TerminusDB team |
| `TERMINUS_DB` | `aurora` | TerminusDB database name |

---

## Documentation

| File | Contents |
|------|----------|
| `AURORA_MASTER_DEMO_GUIDE.md` | Full demo playbook — 5-layer architecture, all 15 scenarios, exec/tech/deep-dive flows |
| `GRAFANA_DEMO_GUIDE.md` | Grafana dashboard walkthrough, panel descriptions, query patterns |
| `TERMINUSDB_DESIGN.md` | TerminusDB schema, PlantState, ScenarioEvent, query examples |
| `MQTT_TOPIC_REFERENCE.md` | All 111 MQTT topics, payload schemas, asset mapping |
| `STABILITY_RUNBOOK.md` | Incident response, health checks, common failure modes |
| `THREE_LAYER_DEMO_GUIDE.md` | IoTAuto + Aurora + AI layer demo structure |
| `CHANGELOG.md` | Full version history with commits |

---

## Roadmap

**Next: AI Layer (`v0.6.0`)**

- MCP server wrapping the Aurora REST API
- Tools: `aurora_status()`, `aurora_set_scenario(id)`, `aurora_trigger_dpp()`, `aurora_query_influx(flux_query)`, `aurora_terminus_query(woql)`
- LLM context injection: live stream snapshot, active scenario AI hint, recent alarms
- Demo agent: auto-narrate fault scenarios, answer "why is OEE dropping?" from live data
- Entry point: `GET /api/predemo` → `ready: true` → hand off to AI agent
