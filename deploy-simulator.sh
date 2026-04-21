#!/usr/bin/env bash
# deploy-simulator.sh  --  UNS Simulator
# Usage:
#   ./deploy-simulator.sh               # codebuild + ecs + frontend
#   ./deploy-simulator.sh codebuild     # zip + CodeBuild image build only
#   ./deploy-simulator.sh ecs           # ECS task register + service update only
#   ./deploy-simulator.sh frontend      # React build + S3 + CloudFront only
set -euo pipefail

REGION="eu-central-1"
ACCOUNT_ID="881490131520"

# Backend
ECR_REPO="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/uns-simulator"
ECS_CLUSTER="pipeline-monitor"
ECS_SERVICE="uns-simulator"
LOG_GROUP="/ecs/uns-simulator"
BUILD_BUCKET="pipeline-monitor-build-881490131520"
CODEBUILD_PROJECT="uns-simulator-build"

# Network
TASK_SG="sg-0c247596e42e0d4a7"
SUBNETS="subnet-0246687326dffa6d3,subnet-06ab06dff7cff4267"
TG_ARN="arn:aws:elasticloadbalancing:eu-central-1:881490131520:targetgroup/uns-simulator-tg/381e14cbc7077089"

# Frontend
S3_BUCKET="uns-simulator-frontend"
CF_DIST_ID="E8FYBFPILTWS8"
FRONTEND_DOMAIN="simulator.iotdemozone.com"
BACKEND_DOMAIN="sim-api.iotdemozone.com"

DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-all}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
step() { echo -e "\n${BLUE}${BOLD}>> $*${NC}"; }
ok()   { echo -e "${GREEN}OK $*${NC}"; }
warn() { echo -e "${YELLOW}WN $*${NC}"; }
die()  { echo -e "${RED}XX $*${NC}"; exit 1; }

echo -e "${BOLD}"
echo "==========================================="
echo " UNS Simulator Deploy -- $(date +%Y-%m-%d\ %H:%M)"
echo "==========================================="
echo -e "${NC}"

# =============================================================================
# CODEBUILD -- zip source + trigger AWS build (no local Docker required)
# =============================================================================
deploy_codebuild() {
  step "Packaging backend source"
  cd "$DIR"
  zip -j /tmp/uns-simulator.zip simulator.py uns_model.py requirements.txt Dockerfile
  ok "Zipped 4 files"

  step "Uploading to s3://$BUILD_BUCKET/source/uns-simulator.zip"
  aws s3 cp /tmp/uns-simulator.zip \
    "s3://$BUILD_BUCKET/source/uns-simulator.zip" --region "$REGION"
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
# ECS -- register task definition + update service + wait for healthy ALB target
# =============================================================================
deploy_ecs() {
  step "Registering ECS task definition"
  TASK_JSON=$(python3 -c "
import json
with open('$DIR/ecs/task-definition.json') as f: td = json.load(f)
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

  step "Waiting for ALB target to become healthy (up to 5 min)"
  for i in $(seq 1 20); do
    sleep 15
    STATE=$(aws elbv2 describe-target-health \
      --target-group-arn "$TG_ARN" --region "$REGION" \
      --query 'TargetHealthDescriptions[?TargetHealth.State==`healthy`] | length(@)' \
      --output text 2>/dev/null || echo 0)
    RUNNING=$(aws ecs describe-services \
      --cluster "$ECS_CLUSTER" --services "$ECS_SERVICE" \
      --region "$REGION" --query 'services[0].runningCount' --output text 2>/dev/null || echo 0)
    echo "  [$i/20] ECS running=$RUNNING  ALB healthy=$STATE"
    [ "$STATE" -ge 1 ] 2>/dev/null && break
  done

  ok "Backend live: https://$BACKEND_DOMAIN"
  echo "  Health:  https://$BACKEND_DOMAIN/health"
  echo "  API:     https://$BACKEND_DOMAIN/api/status"
  echo "  WS:      wss://$BACKEND_DOMAIN/ws"
}

# =============================================================================
# FRONTEND -- npm build -> S3 sync -> CloudFront invalidation
# =============================================================================
deploy_frontend() {
  command -v node >/dev/null 2>&1 || die "node not found"
  STUDIO="$DIR/uns-studio"
  [ -d "$STUDIO" ] || die "uns-studio/ not found at $STUDIO"

  step "npm ci"
  cd "$STUDIO" && npm ci --silent
  ok "Dependencies installed"

  step "npm run build  (API=https://$BACKEND_DOMAIN  WS=wss://$BACKEND_DOMAIN)"
  VITE_API_URL="https://$BACKEND_DOMAIN" \
  VITE_WS_URL="wss://$BACKEND_DOMAIN" \
    npm run build 2>&1 | tail -8
  ok "Build complete -> uns-studio/dist/"

  step "S3 sync to s3://$S3_BUCKET"
  aws s3 sync dist/ "s3://$S3_BUCKET/" --delete \
    --cache-control "public,max-age=31536000,immutable" \
    --exclude "index.html" --region "$REGION"
  aws s3 cp dist/index.html "s3://$S3_BUCKET/index.html" \
    --cache-control "no-cache,no-store,must-revalidate" --region "$REGION"
  ok "S3 sync complete"

  step "CloudFront invalidation $CF_DIST_ID"
  INV=$(aws cloudfront create-invalidation \
    --distribution-id "$CF_DIST_ID" --paths "/*" \
    --query 'Invalidation.Id' --output text)
  ok "Invalidation: $INV"

  echo ""
  echo -e "${GREEN}${BOLD}============================================="
  echo " LIVE:  https://$FRONTEND_DOMAIN"
  echo -e "=============================================${NC}"
}

# =============================================================================
# Main
# =============================================================================
case "$TARGET" in
  codebuild)      deploy_codebuild ;;
  ecs)            deploy_ecs ;;
  frontend|ui)    deploy_frontend ;;
  all|*)
    deploy_codebuild
    deploy_ecs
    deploy_frontend
    ;;
esac

echo -e "\n${GREEN}${BOLD}Deploy complete!${NC}"
warn "Backend logs:  aws logs tail $LOG_GROUP --follow --region $REGION"
warn "ECS events:    aws ecs describe-services --cluster $ECS_CLUSTER --services $ECS_SERVICE --region $REGION --query 'services[0].events[:3]' --output table"
