# Aurora Demo — Stability & Reliability Runbook

> **Last audit:** 2026-04-20 | All systems green

---

## Current State

| Component | Host | Status | Restart policy |
|-----------|------|--------|---------------|
| **aurora-simulator** | ECS Fargate | ✅ running:1 desired:1 | ECS restarts on exit |
| **pipeline-monitor** | ECS Fargate | ✅ running:1 desired:1 | ECS restarts on exit |
| **aurora-aas-sync** | ECS Fargate | ✅ running:1 desired:1 | ECS restarts on exit |
| **uns-simulator** | ECS Fargate | ✅ running:1 desired:1 | ECS restarts on exit |
| **InfluxDB** | EC2 / k8s | ✅ pass | k8s restartPolicy:Always |
| **Grafana** | EC2 / k8s | ✅ ok | k8s restartPolicy:Always |
| **TerminusDB** | EC2 direct | ✅ finalized | systemd / manual |
| **MQTT broker** | EC2 | ✅ connected | systemd |

---

## Pre-Demo Checklist (run 15 min before any demo)

```bash
# Run this one-liner before every demo
bash <(curl -s https://raw.githubusercontent.com/... || cat) << 'EOF'
KEY="acf894b44d993ad68df2d06efe28593c"

echo "1. Simulator health..."
curl -sf https://aurora-api.iotdemozone.com/health || echo "❌ SIMULATOR DOWN"

echo "2. TerminusDB PlantState..."
curl -sf "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=PlantState" \
  -u "admin:8Cv7R#ME" | python3 -c "import sys,json; d=json.load(sys.stdin); print('✅ PlantState:', d['active_scenario'])" \
  || echo "❌ TERMINUSDB DOWN"

echo "3. InfluxDB..."
curl -sf https://influxdb.iotdemozone.com/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('✅ InfluxDB:', d['status'])" \
  || echo "❌ INFLUXDB DOWN"

echo "4. Grafana..."
curl -sf https://grafana.iotdemozone.com/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('✅ Grafana:', d['database'])" \
  || echo "❌ GRAFANA DOWN"

echo "5. Reset scenario to normal..."
curl -sf -X POST https://aurora-api.iotdemozone.com/api/scenario/normal -H "X-API-Key: $KEY" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('✅ Reset:', d['scenario'])"

echo "=== All checks complete ==="
EOF
```

Or as individual commands:
```bash
KEY="acf894b44d993ad68df2d06efe28593c"

# 1. Simulator
curl -s https://aurora-api.iotdemozone.com/health

# 2. TerminusDB PlantState  
curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=PlantState" -u "admin:8Cv7R#ME"

# 3. InfluxDB
curl -s https://influxdb.iotdemozone.com/health

# 4. Grafana
curl -s https://grafana.iotdemozone.com/api/health

# 5. Reset
curl -s -X POST https://aurora-api.iotdemozone.com/api/scenario/normal -H "X-API-Key: $KEY"
```

---

## Known Failure Modes & Recovery

### Failure 1 — Simulator not publishing (MQTT disconnected)

**Symptom:** Grafana panels show "No data" or last value is stale (>30s ago)  
**Check:** `curl -s https://aurora-api.iotdemozone.com/health` → `"mqtt": false`  
**Root cause:** MQTT broker restarted or network hiccup  
**Recovery:**
```bash
# Simulator reconnects automatically within 5s via retry loop
# If stuck after 30s, force ECS task replacement:
aws ecs update-service --cluster pipeline-monitor --service aurora-simulator \
  --force-new-deployment --desired-count 1
# New task starts in ~60s
```

### Failure 2 — TerminusDB not responding

**Symptom:** Scenario triggers succeed but TerminusDB PlantState not updating  
**Check:** `curl -s https://terminusdb.iotdemozone.com/api/ -u "admin:8Cv7R#ME"`  
**Root cause:** EC2 instance rebooted, TerminusDB Docker container stopped  
**Recovery:**
```bash
# SSH to EC2 instance running TerminusDB
# Check container: docker ps | grep terminus
# Restart if stopped: docker start <container_id>
# Or: docker run -d --restart=always -p 6363:6363 terminusdb/terminusdb-server:v11.1.14

# Verify recovery:
curl -s https://terminusdb.iotdemozone.com/api/ -u "admin:8Cv7R#ME"
```
**Note:** TerminusDB data persists on EBS volume — data is not lost on container restart.  
**Demo fallback:** TerminusDB sync is non-blocking. If it's down, simulator and Grafana still work normally. Demo can proceed without the graph layer.

### Failure 3 — Scenario change not reflected in TerminusDB

**Symptom:** `POST /api/scenario/X` returns ok but PlantState still shows old scenario  
**Check:** ECS logs for `[terminus] sync failed`  
**Recovery:** Manually trigger sync:
```bash
curl -s -X POST https://aurora-api.iotdemozone.com/api/scenario/normal \
  -H "X-API-Key: acf894b44d993ad68df2d06efe28593c"
# Then re-trigger your scenario
```

### Failure 4 — Grafana dashboard shows "No data" after scenario switch

**Symptom:** Panels blank after switching scenario  
**Root cause:** Time range is not on "Last 15 minutes" or auto-refresh is off  
**Recovery:** 
1. Set time range to **Last 15 minutes**
2. Enable auto-refresh: **10s**
3. Check Grafana datasource: `https://grafana.iotdemozone.com/connections/datasources`

### Failure 5 — Demo reset leaves stale values

**Symptom:** After reset, Grafana still shows fault values  
**Root cause:** InfluxDB retains old data; panels show last value  
**Recovery:**
```bash
# Reset always returns to normal within 2-3 publish cycles (15-30s)
# Wait 30 seconds after reset before starting next scenario
curl -s -X POST https://aurora-api.iotdemozone.com/api/reset \
  -H "X-API-Key: acf894b44d993ad68df2d06efe28593c"
```

### Failure 6 — ECS task crash/OOM

**Symptom:** Simulator unreachable; ECS shows desired:1 running:0  
**Root cause:** OOM or uncaught exception in simulator  
**Recovery:** ECS automatically replaces the task. Takes ~90s. Check:
```bash
aws ecs describe-services --cluster pipeline-monitor --services aurora-simulator \
  --query 'services[0].{running:runningCount,pending:pendingCount,events:events[:3]}' \
  --output json
```

---

## Manual Recovery Scripts

### Full demo environment reset
```bash
KEY="acf894b44d993ad68df2d06efe28593c"

# 1. Reset simulator
curl -s -X POST https://aurora-api.iotdemozone.com/api/reset -H "X-API-Key: $KEY"

# 2. Sync TerminusDB state
curl -s -X POST https://aurora-api.iotdemozone.com/api/scenario/normal -H "X-API-Key: $KEY"

# 3. Verify
sleep 3 && curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=PlantState" \
  -u "admin:8Cv7R#ME" | python3 -m json.tool
```

### Re-seed TerminusDB if data is lost
```bash
cd /Users/anbernal/uns-simulator
node scripts/seed-terminusdb.js    # Re-seeds schema + assets + scenarios
python3 scripts/reseed-scenarios.py # Re-seeds enriched FaultScenario docs
```

### Force ECS service restart
```bash
aws ecs update-service --cluster pipeline-monitor \
  --service aurora-simulator --force-new-deployment
# Wait 90s then verify:
curl -s https://aurora-api.iotdemozone.com/health
```

---

## Monitoring (Current Gaps)

| Gap | Risk | Priority |
|-----|------|----------|
| No CloudWatch alarm for ECS task failures | Silent downtime before demo | HIGH |
| No TerminusDB uptime monitoring | Demo fails silently | HIGH |
| InfluxDB retention not verified | Data loss after 30 days | MEDIUM |
| No automated pre-demo health check | Manual error-prone check | MEDIUM |
| No MQTT broker monitoring | Silent data gap | MEDIUM |
| Single ECS task (no redundancy) | Single point of failure | LOW (demo env) |

---

## Recommended Next Reliability Improvements

### Priority 1 — CloudWatch alarm for simulator down
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "aurora-simulator-unhealthy" \
  --metric-name HealthyHostCount \
  --namespace AWS/ApplicationELB \
  --dimensions Name=TargetGroup,Value=aurora-simulator-tg/6b80871495f84342 \
  --statistic Minimum --period 60 --threshold 1 \
  --comparison-operator LessThanThreshold --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:eu-central-1:881490131520:demo-alerts \
  --treat-missing-data breaching
```

### Priority 2 — Automated pre-demo health check script
See `scripts/pre-demo-check.sh` (to be created)

### Priority 3 — TerminusDB on ECS with EBS volume
Move TerminusDB from bare EC2 to ECS Fargate with EBS volume for auto-restart.

### Priority 4 — InfluxDB retention policy verification
Verify Aurora bucket has 30-day retention. Set if missing:
```bash
# Via InfluxDB UI: Data → Buckets → Aurora → Edit → Retention: 30 days
```

---

## Quick Status Dashboard (bookmark this)

| URL | What to check |
|-----|--------------|
| `https://aurora-api.iotdemozone.com/health` | Simulator + MQTT + streams |
| `https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=PlantState` | Active scenario + last sync |
| `https://influxdb.iotdemozone.com/health` | InfluxDB ready |
| `https://grafana.iotdemozone.com/api/health` | Grafana database |

---

*Generated: 2026-04-20 | Aurora Industries demo environment*
