#!/bin/bash
# pre-demo-check.sh — Run this 15 minutes before any Aurora demo
# Usage: bash scripts/pre-demo-check.sh
# Exit code: 0 = all green, 1 = one or more failures

KEY="acf894b44d993ad68df2d06efe28593c"
TERMINUS_PASS="8Cv7R#ME"
PASS=0
FAIL=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS+1)); }
fail() { echo -e "  ${RED}✗${NC} $1"; FAIL=$((FAIL+1)); }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  Aurora Demo — Pre-flight Check${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── 1. Simulator ─────────────────────────────────────────────────────────────
echo -e "${BOLD}[1] Aurora Simulator${NC}"
SIM=$(curl -sf --max-time 5 https://aurora-api.iotdemozone.com/health 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$SIM" ]; then
  fail "Simulator unreachable"
else
  RUNNING=$(echo "$SIM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('running',''))" 2>/dev/null)
  MQTT=$(echo "$SIM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('mqtt',''))" 2>/dev/null)
  STREAMS=$(echo "$SIM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('streams',0))" 2>/dev/null)
  UPTIME=$(echo "$SIM" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('uptime',0))" 2>/dev/null)

  [ "$RUNNING" = "True" ] && ok "Simulator running (uptime ${UPTIME}s)" || fail "Simulator not running"
  [ "$MQTT" = "True" ]    && ok "MQTT connected" || fail "MQTT disconnected — Grafana will show no data"
  [ "$STREAMS" -ge 100 ] 2>/dev/null && ok "$STREAMS streams active" || warn "Only $STREAMS streams active (expected 111)"
fi
echo ""

# ── 2. TerminusDB ─────────────────────────────────────────────────────────────
echo -e "${BOLD}[2] TerminusDB${NC}"
PS=$(curl -sf --max-time 5 "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=PlantState" \
  -u "admin:${TERMINUS_PASS}" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$PS" ]; then
  fail "TerminusDB unreachable — graph layer unavailable"
  warn "Simulator + Grafana still work. Demo can proceed without TerminusDB graph layer."
else
  SCENARIO=$(echo "$PS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('active_scenario','').split('/')[-1])" 2>/dev/null)
  LAST_UPDATED=$(echo "$PS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('last_updated','')[-8:])" 2>/dev/null)
  ok "TerminusDB alive — active_scenario: ${SCENARIO} (last updated ${LAST_UPDATED})"

  # Check FaultScenario count
  FSCOUNT=$(curl -sf --max-time 5 "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=FaultScenario&count=20" \
    -u "admin:${TERMINUS_PASS}" 2>/dev/null | grep -c '"@type"')
  [ "$FSCOUNT" -ge 15 ] 2>/dev/null && ok "$FSCOUNT FaultScenario docs found" || fail "Only $FSCOUNT FaultScenario docs (expected 15) — run: python3 scripts/reseed-scenarios.py"
fi
echo ""

# ── 3. InfluxDB ───────────────────────────────────────────────────────────────
echo -e "${BOLD}[3] InfluxDB${NC}"
IDB=$(curl -sf --max-time 5 https://influxdb.iotdemozone.com/health 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$IDB" ]; then
  fail "InfluxDB unreachable — Grafana dashboards will show no data"
else
  STATUS=$(echo "$IDB" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null)
  [ "$STATUS" = "pass" ] && ok "InfluxDB healthy (status: pass)" || fail "InfluxDB status: $STATUS"
fi
echo ""

# ── 4. Grafana ────────────────────────────────────────────────────────────────
echo -e "${BOLD}[4] Grafana${NC}"
GR=$(curl -sf --max-time 5 https://grafana.iotdemozone.com/api/health 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$GR" ]; then
  fail "Grafana unreachable"
else
  DB=$(echo "$GR" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('database',''))" 2>/dev/null)
  VER=$(echo "$GR" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('version',''))" 2>/dev/null)
  [ "$DB" = "ok" ] && ok "Grafana healthy v${VER}" || fail "Grafana database: $DB"
fi
echo ""

# ── 5. Reset to normal ────────────────────────────────────────────────────────
echo -e "${BOLD}[5] Reset to normal scenario${NC}"
RESET=$(curl -sf --max-time 5 -X POST https://aurora-api.iotdemozone.com/api/scenario/normal \
  -H "X-API-Key: ${KEY}" 2>/dev/null)
if [ $? -ne 0 ] || [ -z "$RESET" ]; then
  fail "Reset failed — check simulator"
else
  SC=$(echo "$RESET" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('scenario',''))" 2>/dev/null)
  [ "$SC" = "normal" ] && ok "Reset to normal ✓" || fail "Reset returned unexpected scenario: $SC"
fi
echo ""

# ── 6. Quick scenario smoke test ──────────────────────────────────────────────
echo -e "${BOLD}[6] Scenario smoke test${NC}"
TRIG=$(curl -sf --max-time 5 -X POST https://aurora-api.iotdemozone.com/api/scenario/conveyor_cv01_jam \
  -H "X-API-Key: ${KEY}" 2>/dev/null)
SC2=$(echo "$TRIG" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('scenario',''))" 2>/dev/null)
if [ "$SC2" = "conveyor_cv01_jam" ]; then
  ok "Scenario trigger working (conveyor_cv01_jam)"
  # Reset back
  curl -sf --max-time 5 -X POST https://aurora-api.iotdemozone.com/api/scenario/normal \
    -H "X-API-Key: ${KEY}" > /dev/null 2>&1
  ok "Reset back to normal"
else
  fail "Scenario trigger failed"
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}  ✓ ALL CHECKS PASSED ($PASS/$((PASS+FAIL)))${NC}"
  echo -e "  ${GREEN}Demo environment is ready.${NC}"
else
  echo -e "${RED}${BOLD}  ✗ $FAIL CHECK(S) FAILED ($PASS passed, $FAIL failed)${NC}"
  echo -e "  ${RED}Resolve failures before demo. See STABILITY_RUNBOOK.md${NC}"
fi
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
