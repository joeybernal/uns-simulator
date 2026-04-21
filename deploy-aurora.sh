#!/usr/bin/env bash
# deploy-aurora.sh  —  Aurora Industries UNS Simulator
# Mirrors the uns-simulator deploy pattern exactly.
#
# Usage:
#   ./deploy-aurora.sh               # codebuild + ecs + (no separate frontend — HTML served from FastAPI)
#   ./deploy-aurora.sh codebuild     # zip + CodeBuild image build only
#   ./deploy-aurora.sh ecs           # ECS task register + service update + ALB health wait
#   ./deploy-aurora.sh logs          # tail CloudWatch logs
#   ./deploy-aurora.sh status        # show ECS service status
set -euo pipefail

REGION="eu-central-1"
ACCOUNT_ID="881490131520"

# ── AWS Resources ─────────────────────────────────────────────────────────────
ECR_REPO="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/aurora-simulator"
ECS_CLUSTER="pipeline-monitor"
ECS_SERVICE="aurora-simulator"
LOG_GROUP="/ecs/aurora-simulator"
BUILD_BUCKET="pipeline-monitor-build-881490131520"
CODEBUILD_PROJECT="aurora-simulator-build"

# Network  (reuse same VPC / SGs as uns-simulator)
TASK_SG="sg-0c247596e42e0d4a7"
SUBNETS="subnet-0246687326dffa6d3,subnet-06ab06dff7cff4267"
TG_ARN="arn:aws:elasticloadbalancing:eu-central-1:881490131520:targetgroup/aurora-simulator-tg/6b80871495f84342"

# Domains
BACKEND_DOMAIN="aurora-api.iotdemozone.com"

DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-all}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
step() { echo -e "\n${BLUE}${BOLD}>> $*${NC}"; }
ok()   { echo -e "${GREEN}OK $*${NC}"; }
warn() { echo -e "${YELLOW}WN $*${NC}"; }
die()  { echo -e "${RED}XX $*${NC}"; exit 1; }

echo -e "${BOLD}"
echo "============================================="
echo " Aurora Simulator Deploy  --  $(date '+%Y-%m-%d %H:%M')"
echo "============================================="
echo -e "${NC}"

# =============================================================================
# PRE-FLIGHT: ensure ECR repo + CloudWatch log group exist
# =============================================================================
preflight() {
  step "Pre-flight checks"

  # ECR repo
  aws ecr describe-repositories --repository-names aurora-simulator \
    --region "$REGION" --query 'repositories[0].repositoryUri' --output text \
    2>/dev/null || {
    warn "ECR repo not found — creating aurora-simulator"
    aws ecr create-repository --repository-name aurora-simulator \
      --region "$REGION" \
      --image-scanning-configuration scanOnPush=true \
      --query 'repository.repositoryUri' --output text
  }
  ok "ECR: $ECR_REPO"

  # CloudWatch log group
  aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" \
    --region "$REGION" --query 'logGroups[0].logGroupName' --output text \
    2>/dev/null | grep -q aurora || {
    warn "Log group not found — creating $LOG_GROUP"
    aws logs create-log-group --log-group-name "$LOG_GROUP" --region "$REGION"
    aws logs put-retention-policy --log-group-name "$LOG_GROUP" \
      --retention-in-days 7 --region "$REGION"
  }
  ok "Log group: $LOG_GROUP"
}

# =============================================================================
# CODEBUILD — zip source files + trigger build in AWS (no local Docker needed)
# =============================================================================
deploy_codebuild() {
  step "Packaging Aurora backend source"
  cd "$DIR"

  # Zip exactly the files needed
  zip -j /tmp/aurora-simulator.zip \
    aurora_simulator.py \
    aurora_model.py \
    requirements-aurora.txt \
    Dockerfile.aurora

  # Include static dashboard
  mkdir -p /tmp/aurora-build/static
  cp static/aurora.html /tmp/aurora-build/static/
  cd /tmp/aurora-build && zip -r /tmp/aurora-simulator.zip static/
  cd "$DIR"

  ok "Zipped aurora_simulator.py + aurora_model.py + static/aurora.html + Dockerfile.aurora"

  step "Uploading to s3://$BUILD_BUCKET/source/aurora-simulator.zip"
  aws s3 cp /tmp/aurora-simulator.zip \
    "s3://$BUILD_BUCKET/source/aurora-simulator.zip" --region "$REGION"
  ok "Uploaded"

  step "Starting CodeBuild project $CODEBUILD_PROJECT"
  BUILD_ID=$(aws codebuild start-build \
    --project-name "$CODEBUILD_PROJECT" --region "$REGION" \
    --query 'build.id' --output text)
  ok "Build: $BUILD_ID"

  step "Waiting for CodeBuild (up to 10 min)"
  for i in $(seq 1 40); do
    sleep 15
    RESULT=$(aws codebuild batch-get-builds --ids "$BUILD_ID" --region "$REGION" \
      --query 'builds[0].{phase:currentPhase,status:buildStatus}' --output text 2>/dev/null)
    echo "  [$i/40] $RESULT"
    echo "$RESULT" | grep -q "SUCCEEDED" && { ok "Image pushed: $ECR_REPO:latest"; return; }
    echo "$RESULT" | grep -qE "FAILED|FAULT|STOPPED" && die "CodeBuild failed: $RESULT"
  done
  die "CodeBuild timed out"
}

# =============================================================================
# ECS — register task definition + update service + wait for healthy ALB target
# =============================================================================
deploy_ecs() {
  step "Registering ECS task definition"
  TASK_JSON=$(python3 -c "
import json
with open('$DIR/ecs/task-definition-aurora.json') as f: td = json.load(f)
td['containerDefinitions'][0]['image'] = '$ECR_REPO:latest'
print(json.dumps(td))")

  TASK_ARN=$(aws ecs register-task-definition \
    --cli-input-json "$TASK_JSON" --region "$REGION" \
    --query 'taskDefinition.taskDefinitionArn' --output text)
  ok "Task: $TASK_ARN"

  step "Updating ECS service $ECS_SERVICE"
  aws ecs update-service \
    --cluster "$ECS_CLUSTER" --service "$ECS_SERVICE" \
    --task-definition "$TASK_ARN" --force-new-deployment \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$TASK_SG],assignPublicIp=ENABLED}" \
    --region "$REGION" \
    --query 'service.{status:status,desired:desiredCount}' --output table
  ok "Service update triggered"

  step "Waiting for ECS task to become healthy (up to 5 min)"
  for i in $(seq 1 20); do
    sleep 15
    RUNNING=$(aws ecs describe-services \
      --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE" \
      --region "$REGION" --query 'services[0].runningCount' --output text 2>/dev/null || echo 0)
    echo "  [$i/20] ECS running=$RUNNING"
    [ "$RUNNING" -ge 1 ] 2>/dev/null && break
  done

  ok "Backend live: https://$BACKEND_DOMAIN"
  echo "  Health:  https://$BACKEND_DOMAIN/health"
  echo "  API:     https://$BACKEND_DOMAIN/api/status"
  echo "  WS:      wss://$BACKEND_DOMAIN/ws"
  echo "  UI:      https://$BACKEND_DOMAIN/"
}

# =============================================================================
# LOCAL  — quick local Docker test before deploying
# =============================================================================
local_test() {
  step "Building Docker image locally"
  docker build -f Dockerfile.aurora -t aurora-simulator:local .
  ok "Image built"

  step "Running locally on port 8081"
  docker run --rm -d --name aurora-test -p 8081:8081 \
    -e MQTT_HOST=mqtt.iotdemozone.com \
    -e MQTT_USER=admin \
    -e MQTT_PASS="${MQTT_PASS:-}" \
    aurora-simulator:local
  sleep 3
  curl -sf http://localhost:8081/health | python3 -m json.tool
  ok "Health check passed"
  docker stop aurora-test
}

# =============================================================================
# STATUS / LOGS
# =============================================================================
show_status() {
  aws ecs describe-services \
    --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE" \
    --region "$REGION" \
    --query 'services[0].{status:status,running:runningCount,desired:desiredCount,pending:pendingCount}' \
    --output table 2>/dev/null || echo "Service not found — not yet deployed"
}

show_logs() {
  echo "Tailing $LOG_GROUP ..."
  aws logs tail "$LOG_GROUP" --follow --region "$REGION"
}

# =============================================================================
# Main
# =============================================================================
case "$TARGET" in
  preflight)          preflight ;;
  codebuild|build)    preflight; deploy_codebuild ;;
  ecs|service)        deploy_ecs ;;
  local)              local_test ;;
  status)             show_status ;;
  logs)               show_logs ;;
  all|*)
    preflight
    deploy_codebuild
    deploy_ecs
    ;;
esac

echo -e "\n${GREEN}${BOLD}Deploy complete!${NC}"
warn "Logs:    aws logs tail $LOG_GROUP --follow --region $REGION"
warn "Status:  aws ecs describe-services --cluster $ECS_CLUSTER --services $ECS_SERVICE --region $REGION --query 'services[0].events[:3]' --output table"
warn "Health:  curl https://$BACKEND_DOMAIN/health"
