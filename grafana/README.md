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

## Datasource

- **Type:** InfluxDB (Flux)
- **UID:** `cfgvijnkiwk5ca`
- **Bucket:** `Aurora`
- **Org:** `Deloitte`
- **URL:** `http://influxdb-svc.influxdb.svc.cluster.local`
