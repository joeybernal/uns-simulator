# Aurora Grafana Dashboards

Live dashboards for the Aurora Industries digital twin, pulling from InfluxDB (bucket: `Aurora`, org: `Deloitte`).

## Dashboards

| File | UID | Title |
|------|-----|-------|
| `aurora-nav-home.json` | `aurora-nav-home` | Aurora — Navigation Home |
| `aurora-plant-overview.json` | `aurora-plant-overview` | 4. Aurora — Plant Overview |
| `aurora-asset-telemetry.json` | `aurora-asset-telemetry` | 5. Aurora — Asset Telemetry |
| `aurora-power-monitoring.json` | `aurora-power-monitoring` | 6. Aurora — Power & Energy Monitoring |
| `aurora-faults-alarms.json` | `aurora-faults-alarms` | 7. Aurora — Faults, Alarms & Scenario History |
| `aurora-mes-batch.json` | `aurora-mes-batch` | 8. MES / Batch Lifecycle & DPP |

## Navigation

All dashboards include a **top navigation link bar** to jump between dashboards.  
Start at the **Navigation Home** for a live KPI overview and clickable cards.

URL: `https://grafana.iotdemozone.com/d/aurora-nav-home`

## Import

To re-import all dashboards via the Grafana API:

```bash
GF="https://grafana.iotdemozone.com"
GFAUTH="admin:<password>"
for f in dashboards/*.json; do
  echo "Uploading $f..."
  curl -s -X POST "$GF/api/dashboards/db" \
    -u "$GFAUTH" \
    -H "Content-Type: application/json" \
    -d @"$f" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status'), d.get('url',''))"
done
```

## Datasources

### 1. InfluxDB (primary telemetry)

- **Type:** InfluxDB (Flux)
- **UID:** `cfgvijnkiwk5ca`
- **Bucket:** `Aurora`
- **Org:** `Deloitte`
- **URL:** `http://influxdb-svc.influxdb.svc.cluster.local`

### 2. TerminusDB via Infinity (graph context layer)

The `aurora-faults-alarms` dashboard now includes 4 panels pulling from TerminusDB
for the **digital twin context layer** (scenario events, asset status, AI hints).

- **Plugin:** [yesoreyeram-infinity-datasource](https://grafana.com/grafana/plugins/yesoreyeram-infinity-datasource/)
- **UID:** `terminus-infinity` ← must match this exactly when creating the datasource
- **URL:** `https://terminusdb.iotdemozone.com`
- **Auth:** Basic auth — `admin` / (from AWS secret `aurora-simulator/terminus-pass`)

#### Setup steps (one-time)

1. Install plugin: `grafana-cli plugins install yesoreyeram-infinity-datasource`  
   Or add to Helm values: `plugins: ["yesoreyeram-infinity-datasource"]`

2. Create datasource via UI or API:
```bash
GF="https://grafana.iotdemozone.com"
GFAUTH="admin:<password>"
curl -s -X POST "$GF/api/datasources" \
  -u "$GFAUTH" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TerminusDB",
    "type": "yesoreyeram-infinity-datasource",
    "uid": "terminus-infinity",
    "access": "proxy",
    "url": "https://terminusdb.iotdemozone.com",
    "basicAuth": true,
    "basicAuthUser": "admin",
    "secureJsonData": {"basicAuthPassword": "<terminus-pass>"},
    "jsonData": {"allowedHosts": ["https://terminusdb.iotdemozone.com"]},
    "isDefault": false
  }'
```

#### TerminusDB panels in `aurora-faults-alarms`

| Panel | ID | Description |
|-------|----|-------------|
| Section header | 49 | Markdown divider |
| Scenario Event History | 50 | All ScenarioEvent docs — activated_at, duration, triggered_by |
| Asset Operational Status | 51 | All Asset docs — area, type, operational_status, health_score |
| Active Scenario AI Context | 52 | All FaultScenario docs — label, severity, ai_hint, root_cause |

Data is updated live from TerminusDB; the aurora-simulator writes a new `ScenarioEvent`
and updates `PlantState` on every scenario change (via `TERMINUS_PASS` secret).

#### Seed / re-seed TerminusDB

```bash
cd uns-simulator
# Uses .venv or any Python env with requests installed
python3 scripts/seed-terminusdb.py
```
