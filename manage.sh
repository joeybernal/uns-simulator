#!/usr/bin/env bash
# manage.sh — UNS Simulator capacity & demo management
#
# Usage:
#   ./manage.sh status           Show current ECS + API state
#   ./manage.sh up               Scale ECS to 1 (start the task)
#   ./manage.sh down             Scale ECS to 0 (free capacity, ~$0 cost)
#   ./manage.sh demo             Scale up, wait for healthy, then reset for demo
#   ./manage.sh reset            POST /api/reset  (clears drift/wear, scenario→normal)
#   ./manage.sh start            POST /api/start  (begin publishing)
#   ./manage.sh stop             POST /api/stop   (pause publishing, task stays up)
#   ./manage.sh scenario <id>    POST /api/scenario/<id>
#   ./manage.sh logs             Tail CloudWatch logs live
#   ./manage.sh scenarios        List all available scenario IDs

set -euo pipefail

CLUSTER="pipeline-monitor"
SERVICE="uns-simulator"
REGION="eu-central-1"
TG_ARN="arn:aws:elasticloadbalancing:eu-central-1:881490131520:targetgroup/uns-simulator-tg/381e14cbc7077089"
API="https://sim-api.iotdemozone.com"

# ── colours ──────────────────────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[0;34m'
BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${G}✓  $*${NC}"; }
warn() { echo -e "${Y}⚠  $*${NC}"; }
err()  { echo -e "${R}✗  $*${NC}"; }
step() { echo -e "\n${B}${BOLD}▶  $*${NC}"; }

# ── helpers ───────────────────────────────────────────────────────────────────
_ecs_desired() {
    aws ecs describe-services \
        --cluster "$CLUSTER" --services "$SERVICE" --region "$REGION" \
        --query 'services[0].desiredCount' --output text 2>/dev/null || echo "?"
}

_ecs_running() {
    aws ecs describe-services \
        --cluster "$CLUSTER" --services "$SERVICE" --region "$REGION" \
        --query 'services[0].runningCount' --output text 2>/dev/null || echo "?"
}

_alb_healthy() {
    aws elbv2 describe-target-health \
        --target-group-arn "$TG_ARN" --region "$REGION" \
        --query "length(TargetHealthDescriptions[?TargetHealth.State=='healthy'])" \
        --output text 2>/dev/null || echo "0"
}

_api_status() {
    curl -sk --max-time 6 "$API/api/status" 2>/dev/null
}

_api_post() {
    curl -sk --max-time 8 -X POST "$API$1" \
        -H "Content-Type: application/json" 2>/dev/null
}

_scale() {
    aws ecs update-service \
        --cluster "$CLUSTER" --services "$SERVICE" \
        --desired-count "$1" --region "$REGION" \
        --query 'service.desiredCount' --output text 2>/dev/null
}

_wait_healthy() {
    local max="${1:-24}" i
    for i in $(seq 1 "$max"); do
        local h; h=$(_alb_healthy)
        local r; r=$(_ecs_running)
        echo "  [${i}/${max}] ECS running=${r}  ALB healthy=${h}"
        [ "${h:-0}" -ge 1 ] 2>/dev/null && return 0
        sleep 15
    done
    return 1
}

_wait_drained() {
    local max=12 i
    for i in $(seq 1 $max); do
        local r; r=$(_ecs_running)
        echo "  [${i}/${max}] ECS running=${r}"
        [ "${r:-1}" -eq 0 ] 2>/dev/null && return 0
        sleep 10
    done
    return 1
}

# ── commands ──────────────────────────────────────────────────────────────────
cmd_status() {
    echo -e "\n${BOLD}UNS Simulator — Status${NC}"
    echo "────────────────────────────────────"

    local desired; desired=$(_ecs_desired)
    local running; running=$(_ecs_running)
    local healthy; healthy=$(_alb_healthy)

    echo "ECS  desired=${desired}  running=${running}  ALB healthy=${healthy}"

    if [ "${healthy:-0}" -ge 1 ] 2>/dev/null; then
        local s; s=$(_api_status)
        if [ -n "$s" ]; then
            echo "$s" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(f'API  running={d[\"running\"]}  mqtt={d[\"mqtt_connected\"]}  '
      f'rate={d[\"rate\"]}msg/s  total={d[\"total_published\"]:,}  '
      f'scenario={d[\"scenario\"]}  uptime={d.get(\"uptime\",0)}s')
" 2>/dev/null || echo "API  (parse error)"
        else
            warn "API  not responding"
        fi
    else
        warn "API  not reachable (task not running)"
    fi
    echo ""
}

cmd_up() {
    step "Scaling ECS service to 1"
    local current; current=$(_ecs_desired)
    if [ "$current" = "1" ] && [ "$(_ecs_running)" = "1" ]; then
        ok "Already running — nothing to do"
        return
    fi
    _scale 1 > /dev/null
    ok "Desired count → 1"
    step "Waiting for task to be healthy (up to 6 min)…"
    if _wait_healthy 24; then
        ok "Task is healthy"
    else
        err "Timed out waiting for healthy — check: ./manage.sh logs"
        exit 1
    fi
    cmd_status
}

cmd_down() {
    step "Scaling ECS service to 0  (no running tasks = no cost)"
    local h; h=$(_alb_healthy)
    if [ "${h:-0}" -ge 1 ] 2>/dev/null; then
        # Gracefully stop publishing first
        _api_post "/api/stop" > /dev/null 2>&1 || true
        sleep 2
    fi
    _scale 0 > /dev/null
    ok "Desired count → 0"
    step "Waiting for task to drain…"
    if _wait_drained; then
        ok "Task stopped  •  Fargate cost: \$0.00/hr"
    else
        warn "Task may still be draining — verify with: ./manage.sh status"
    fi
}

cmd_demo() {
    echo -e "\n${BOLD}${G}Demo prep — scale up + reset${NC}"
    echo "────────────────────────────────────"

    # 1. Ensure task is running
    local current; current=$(_ecs_desired)
    if [ "$current" != "1" ] || [ "$(_ecs_running)" != "1" ]; then
        step "Starting ECS task…"
        _scale 1 > /dev/null
        if ! _wait_healthy 24; then
            err "Task failed to start — check logs"
            exit 1
        fi
    else
        ok "Task already running"
    fi

    # 2. Wait a few seconds for FastAPI startup to complete
    sleep 5

    # 3. Reset to clean demo state
    step "Resetting demo state (clearing drift/wear/counts)…"
    local resp; resp=$(_api_post "/api/reset")
    echo "$resp" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('  ' + d.get('message','done'))
" 2>/dev/null || warn "Reset response: $resp"

    ok "Demo ready!"
    echo ""
    echo "  Frontend:  https://simulator.iotdemozone.com"
    echo "  API:       https://sim-api.iotdemozone.com/api/status"
    echo "  WebSocket: wss://sim-api.iotdemozone.com/ws"
    echo ""
    echo "  Quick scenario switch:"
    echo "    ./manage.sh scenario ecoat_bath_contamination"
    echo "    ./manage.sh scenario curing_oven_temp_runaway"
    echo "    ./manage.sh scenario normal"
    echo ""
    cmd_status
}

cmd_reset() {
    step "Resetting demo state"
    local resp; resp=$(_api_post "/api/reset")
    echo "$resp" | python3 -c "
import json,sys
d=json.load(sys.stdin)
ok = d.get('ok', False)
print('  running=' + str(d.get('running')) + '  ' + d.get('message',''))
exit(0 if ok else 1)
" 2>/dev/null || { err "Reset failed — is the task running? Try: ./manage.sh up"; exit 1; }
    ok "Reset complete"
}

cmd_start() {
    step "Starting publishing"
    _api_post "/api/start" | python3 -c "
import json,sys; d=json.load(sys.stdin); print('  running=' + str(d.get('running')))
" 2>/dev/null
    ok "Publishing started"
}

cmd_stop() {
    step "Stopping publishing (task remains up)"
    _api_post "/api/stop" | python3 -c "
import json,sys; d=json.load(sys.stdin); print('  running=' + str(d.get('running')))
" 2>/dev/null
    ok "Publishing stopped"
}

cmd_scenario() {
    local id="${1:-}"
    if [ -z "$id" ]; then
        err "Usage: ./manage.sh scenario <scenario_id>"
        cmd_scenarios
        exit 1
    fi
    step "Setting scenario: $id"
    local resp; resp=$(_api_post "/api/scenario/$id")
    echo "$resp" | python3 -c "
import json,sys
d=json.load(sys.stdin)
if d.get('ok'): print('  scenario → ' + d.get('scenario','?'))
else: print('  ERROR: ' + d.get('error','unknown'))
" 2>/dev/null || warn "Response: $resp"
}

cmd_logs() {
    step "Tailing CloudWatch logs  (Ctrl+C to stop)"
    aws logs tail "/ecs/${SERVICE}" --follow --region "$REGION" 2>/dev/null
}

cmd_scenarios() {
    echo ""
    echo -e "${BOLD}Available scenario IDs:${NC}"
    curl -sk "$API/api/status" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for sc in d.get('scenarios',[]):
    active = ' ◀ active' if sc['id'] == d.get('scenario') else ''
    print(f'  {sc[\"id\"]:<40} {sc[\"label\"]}{active}')
" 2>/dev/null || echo "  (API not reachable)"
}

# ── dispatch ──────────────────────────────────────────────────────────────────
CMD="${1:-status}"
shift || true

case "$CMD" in
    status)           cmd_status ;;
    up)               cmd_up ;;
    down)             cmd_down ;;
    demo)             cmd_demo ;;
    reset)            cmd_reset ;;
    start)            cmd_start ;;
    stop)             cmd_stop ;;
    scenario)         cmd_scenario "$@" ;;
    logs)             cmd_logs ;;
    scenarios)        cmd_scenarios ;;
    *)
        echo "Usage: ./manage.sh {status|up|down|demo|reset|start|stop|scenario <id>|logs|scenarios}"
        exit 1
        ;;
esac
