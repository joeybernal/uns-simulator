#!/usr/bin/env bash
# setup-aurora-infra.sh
# ─────────────────────────────────────────────────────────────────────────────
# One-time AWS infrastructure setup for the Aurora Industries UNS Simulator.
# Run this ONCE before deploy-aurora.sh.
#
# Creates:
#   1. ECR repository          aurora-simulator
#   2. CloudWatch log group    /ecs/aurora-simulator
#   3. Secrets Manager secret  aurora-simulator/mqtt-pass  (value: $MQTT_PASS)
#   4. ECS target group        aurora-simulator-tg  (port 8081, HTTP, health /health)
#   5. ALB listener rule       aurora-api.iotdemozone.com → aurora-simulator-tg
#   6. CodeBuild project       aurora-simulator-build  (clone of uns-simulator-build)
#   7. ECS service             aurora-simulator
#   8. Route 53 A-alias        aurora-api.iotdemozone.com → uns-simulator-alb
#
# Usage:
#   MQTT_PASS=<password> ./setup-aurora-infra.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config (matches deploy-aurora.sh) ─────────────────────────────────────────
REGION="eu-central-1"
ACCOUNT_ID="881490131520"

ECR_REPO_NAME="aurora-simulator"
ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO_NAME"

LOG_GROUP="/ecs/aurora-simulator"
SECRET_NAME="aurora-simulator/mqtt-pass"

# VPC / network — same as uns-simulator
VPC_ID="vpc-056f9780858233091"

SUBNETS="subnet-0246687326dffa6d3,subnet-06ab06dff7cff4267"
TASK_SG="sg-0c247596e42e0d4a7"

# ALB
ALB_NAME="uns-simulator-alb"
ALB_ARN=$(aws elbv2 describe-load-balancers --names "$ALB_NAME" \
  --region "$REGION" --query 'LoadBalancers[0].LoadBalancerArn' --output text)
HTTPS_LISTENER_ARN=$(aws elbv2 describe-listeners \
  --load-balancer-arn "$ALB_ARN" --region "$REGION" \
  --query 'Listeners[?Port==`443`].ListenerArn | [0]' --output text)

# ECS
ECS_CLUSTER="pipeline-monitor"
ECS_SERVICE="aurora-simulator"
TASK_ROLE="arn:aws:iam::$ACCOUNT_ID:role/pipeline-monitor-ecs-task-role"
EXEC_ROLE="arn:aws:iam::$ACCOUNT_ID:role/pipeline-monitor-ecs-execution-role"
BUILD_BUCKET="pipeline-monitor-build-$ACCOUNT_ID"
CODEBUILD_PROJECT="aurora-simulator-build"
CODEBUILD_ROLE=$(aws codebuild batch-get-projects --names uns-simulator-build \
  --region "$REGION" --query 'projects[0].serviceRole' --output text)

# Route53
HOSTED_ZONE_ID="Z04185432HG4DCCGVQBV1"
BACKEND_DOMAIN="aurora-api.iotdemozone.com"
ALB_DNS=$(aws elbv2 describe-load-balancers --names "$ALB_NAME" \
  --region "$REGION" --query 'LoadBalancers[0].DNSName' --output text)
ALB_ZONE=$(aws elbv2 describe-load-balancers --names "$ALB_NAME" \
  --region "$REGION" --query 'LoadBalancers[0].CanonicalHostedZoneId' --output text)

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
step() { echo -e "\n${BLUE}${BOLD}>> $*${NC}"; }
ok()   { echo -e "${GREEN}✓  $*${NC}"; }
skip() { echo -e "${YELLOW}→  $*  (already exists)${NC}"; }
die()  { echo -e "${RED}✗  $*${NC}"; exit 1; }

echo -e "${BOLD}"
echo "════════════════════════════════════════════════"
echo " Aurora Simulator — One-Time Infra Setup"
echo " Region:  $REGION"
echo " Account: $ACCOUNT_ID"
echo "════════════════════════════════════════════════"
echo -e "${NC}"

# ─────────────────────────────────────────────────────────────────────────────
# 1. ECR repository
# ─────────────────────────────────────────────────────────────────────────────
step "1/8  ECR repository"
if aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" \
     --region "$REGION" &>/dev/null; then
  skip "ECR repo $ECR_REPO_NAME"
else
  aws ecr create-repository --repository-name "$ECR_REPO_NAME" \
    --region "$REGION" \
    --image-scanning-configuration scanOnPush=true \
    --image-tag-mutability MUTABLE \
    --query 'repository.repositoryUri' --output text
  ok "Created ECR repo: $ECR_URI"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 2. CloudWatch log group
# ─────────────────────────────────────────────────────────────────────────────
step "2/8  CloudWatch log group"
if aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" \
     --region "$REGION" --query 'logGroups[0].logGroupName' --output text \
     2>/dev/null | grep -q aurora; then
  skip "$LOG_GROUP"
else
  aws logs create-log-group --log-group-name "$LOG_GROUP" --region "$REGION"
  aws logs put-retention-policy --log-group-name "$LOG_GROUP" \
    --retention-in-days 7 --region "$REGION"
  ok "Created log group $LOG_GROUP (7-day retention)"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 3. Secrets Manager — MQTT password
# ─────────────────────────────────────────────────────────────────────────────
step "3/8  Secrets Manager ($SECRET_NAME)"
if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" \
     --region "$REGION" &>/dev/null; then
  skip "Secret $SECRET_NAME"
else
  MQTT_PASS="${MQTT_PASS:-}"
  [ -z "$MQTT_PASS" ] && die "MQTT_PASS env var required. Run: MQTT_PASS=<password> $0"
  SECRET_ARN=$(aws secretsmanager create-secret \
    --name "$SECRET_NAME" \
    --description "MQTT password for Aurora simulator" \
    --secret-string "{\"mqtt_pass\":\"$MQTT_PASS\"}" \
    --region "$REGION" \
    --query 'ARN' --output text)
  ok "Created secret: $SECRET_ARN"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 4. Target group (port 8081, health /health)
# ─────────────────────────────────────────────────────────────────────────────
step "4/8  Target group aurora-simulator-tg"
TG_ARN=$(aws elbv2 describe-target-groups --names "aurora-simulator-tg" \
  --region "$REGION" --query 'TargetGroups[0].TargetGroupArn' --output text \
  2>/dev/null || echo "")
if [ -n "$TG_ARN" ] && [ "$TG_ARN" != "None" ]; then
  skip "Target group aurora-simulator-tg ($TG_ARN)"
else
  TG_ARN=$(aws elbv2 create-target-group \
    --name "aurora-simulator-tg" \
    --protocol HTTP \
    --port 8081 \
    --vpc-id "$VPC_ID" \
    --target-type ip \
    --health-check-protocol HTTP \
    --health-check-path "/health" \
    --health-check-interval-seconds 30 \
    --health-check-timeout-seconds 10 \
    --healthy-threshold-count 2 \
    --unhealthy-threshold-count 3 \
    --region "$REGION" \
    --query 'TargetGroups[0].TargetGroupArn' --output text)
  ok "Created target group: $TG_ARN"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 5. ALB listener rule — host-header aurora-api.iotdemozone.com
# ─────────────────────────────────────────────────────────────────────────────
step "5/8  ALB listener rule (host: $BACKEND_DOMAIN)"
EXISTING_RULE=$(aws elbv2 describe-rules --listener-arn "$HTTPS_LISTENER_ARN" \
  --region "$REGION" \
  --query "Rules[?Conditions[?Values[?contains(@,\`$BACKEND_DOMAIN\`)]]].RuleArn | [0]" \
  --output text 2>/dev/null || echo "")
if [ -n "$EXISTING_RULE" ] && [ "$EXISTING_RULE" != "None" ]; then
  skip "ALB rule for $BACKEND_DOMAIN ($EXISTING_RULE)"
else
  RULE_ARN=$(aws elbv2 create-rule \
    --listener-arn "$HTTPS_LISTENER_ARN" \
    --region "$REGION" \
    --priority 20 \
    --conditions '[{"Field":"host-header","Values":["'"$BACKEND_DOMAIN"'"]}]' \
    --actions '[{"Type":"forward","TargetGroupArn":"'"$TG_ARN"'"}]' \
    --query 'Rules[0].RuleArn' --output text)
  ok "Created ALB rule (priority 20): $RULE_ARN"
  # Also add HTTP→HTTPS redirect rule
  HTTP_LISTENER_ARN=$(aws elbv2 describe-listeners \
    --load-balancer-arn "$ALB_ARN" --region "$REGION" \
    --query 'Listeners[?Port==`80`].ListenerArn | [0]' --output text)
  aws elbv2 create-rule \
    --listener-arn "$HTTP_LISTENER_ARN" \
    --region "$REGION" \
    --priority 20 \
    --conditions '[{"Field":"host-header","Values":["'"$BACKEND_DOMAIN"'"]}]' \
    --actions '[{"Type":"redirect","RedirectConfig":{"Protocol":"HTTPS","Port":"443","StatusCode":"HTTP_301"}}]' \
    --query 'Rules[0].RuleArn' --output text
  ok "Created HTTP→HTTPS redirect rule"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 6. CodeBuild project
# ─────────────────────────────────────────────────────────────────────────────
step "6/8  CodeBuild project ($CODEBUILD_PROJECT)"
if aws codebuild batch-get-projects --names "$CODEBUILD_PROJECT" \
     --region "$REGION" --query 'projects[0].name' --output text \
     2>/dev/null | grep -q aurora; then
  skip "CodeBuild project $CODEBUILD_PROJECT"
else
  BUILDSPEC='version: 0.2
phases:
  pre_build:
    commands:
      - aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $ECR_URI
  build:
    commands:
      - docker build -f Dockerfile.aurora -t $ECR_URI:latest .
      - docker tag $ECR_URI:latest $ECR_URI:$CODEBUILD_BUILD_NUMBER
  post_build:
    commands:
      - docker push $ECR_URI:latest
      - docker push $ECR_URI:$CODEBUILD_BUILD_NUMBER
      - echo Build complete'

  aws codebuild create-project \
    --name "$CODEBUILD_PROJECT" \
    --region "$REGION" \
    --source "{\"type\":\"S3\",\"location\":\"$BUILD_BUCKET/source/aurora-simulator.zip\",\"buildspec\":$(echo "$BUILDSPEC" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}" \
    --artifacts '{"type":"NO_ARTIFACTS"}' \
    --environment "{\"type\":\"LINUX_CONTAINER\",\"image\":\"aws/codebuild/standard:7.0\",\"computeType\":\"BUILD_GENERAL1_SMALL\",\"privilegedMode\":true,\"environmentVariables\":[{\"name\":\"ECR_URI\",\"value\":\"$ECR_URI\",\"type\":\"PLAINTEXT\"}]}" \
    --service-role "$CODEBUILD_ROLE" \
    --query 'project.arn' --output text
  ok "Created CodeBuild project $CODEBUILD_PROJECT"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 7. ECS service
# ─────────────────────────────────────────────────────────────────────────────
step "7/8  ECS service ($ECS_SERVICE)"
EXISTING_SVC=$(aws ecs describe-services --cluster "$ECS_CLUSTER" \
  --services "$ECS_SERVICE" --region "$REGION" \
  --query 'services[?status!=`INACTIVE`].serviceArn | [0]' --output text 2>/dev/null || echo "")
if [ -n "$EXISTING_SVC" ] && [ "$EXISTING_SVC" != "None" ]; then
  skip "ECS service $ECS_SERVICE"
else
  # Register a stub task definition first (will be overwritten by deploy-aurora.sh)
  SECRET_ARN=$(aws secretsmanager describe-secret --secret-id "$SECRET_NAME" \
    --region "$REGION" --query 'ARN' --output text)
  TASK_DEF_JSON=$(cat <<EOF
{
  "family": "aurora-simulator",
  "taskRoleArn": "$TASK_ROLE",
  "executionRoleArn": "$EXEC_ROLE",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [{
    "name": "aurora-simulator",
    "image": "public.ecr.aws/docker/library/python:3.12-slim",
    "essential": true,
    "portMappings": [{"containerPort": 8081, "hostPort": 8081, "protocol": "tcp"}],
    "environment": [
      {"name": "MQTT_HOST", "value": "mqtt.iotdemozone.com"},
      {"name": "MQTT_PORT", "value": "1883"},
      {"name": "MQTT_USER", "value": "admin"},
      {"name": "AURORA_PORT", "value": "8081"}
    ],
    "secrets": [{"name": "MQTT_PASS", "valueFrom": "$SECRET_ARN:mqtt_pass::"}],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "$LOG_GROUP",
        "awslogs-region": "$REGION",
        "awslogs-stream-prefix": "ecs"
      }
    },
    "command": ["python3", "-c", "import time; time.sleep(3600)"]
  }]
}
EOF
  )
  TASK_ARN=$(aws ecs register-task-definition \
    --cli-input-json "$TASK_DEF_JSON" --region "$REGION" \
    --query 'taskDefinition.taskDefinitionArn' --output text)
  ok "Registered stub task definition: $TASK_ARN"

  aws ecs create-service \
    --cluster "$ECS_CLUSTER" \
    --service-name "$ECS_SERVICE" \
    --task-definition "$TASK_ARN" \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$TASK_SG],assignPublicIp=ENABLED}" \
    --load-balancers "[{\"targetGroupArn\":\"$TG_ARN\",\"containerName\":\"aurora-simulator\",\"containerPort\":8081}]" \
    --health-check-grace-period-seconds 60 \
    --region "$REGION" \
    --query 'service.{arn:serviceArn,status:status}' --output table
  ok "Created ECS service $ECS_SERVICE"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 8. Route 53 DNS record
# ─────────────────────────────────────────────────────────────────────────────
step "8/8  Route 53 — $BACKEND_DOMAIN"
EXISTING_DNS=$(aws route53 list-resource-record-sets \
  --hosted-zone-id "$HOSTED_ZONE_ID" \
  --query "ResourceRecordSets[?Name==\`$BACKEND_DOMAIN.\`].Name | [0]" \
  --output text 2>/dev/null || echo "")
if [ -n "$EXISTING_DNS" ] && [ "$EXISTING_DNS" != "None" ]; then
  skip "DNS record $BACKEND_DOMAIN"
else
  aws route53 change-resource-record-sets \
    --hosted-zone-id "$HOSTED_ZONE_ID" \
    --change-batch "{
      \"Changes\": [{
        \"Action\": \"CREATE\",
        \"ResourceRecordSet\": {
          \"Name\": \"$BACKEND_DOMAIN\",
          \"Type\": \"A\",
          \"AliasTarget\": {
            \"HostedZoneId\": \"$ALB_ZONE\",
            \"DNSName\": \"dualstack.$ALB_DNS\",
            \"EvaluateTargetHealth\": true
          }
        }
      }]
    }" --query 'ChangeInfo.Status' --output text
  ok "Created DNS A-alias $BACKEND_DOMAIN → $ALB_DNS"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Print TG ARN for deploy-aurora.sh
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}════════════════════════════════════════════════"
echo " Infrastructure ready!"
echo "════════════════════════════════════════════════${NC}"
echo ""
echo "Target Group ARN:"
echo "  $TG_ARN"
echo ""
echo "Update deploy-aurora.sh line:"
echo "  TG_ARN=\"$TG_ARN\""
echo ""
echo "Next step — deploy the container image:"
echo "  ./deploy-aurora.sh codebuild   # build + push image to ECR"
echo "  ./deploy-aurora.sh ecs         # register task def + update service"
echo ""
echo "Or both at once:"
echo "  ./deploy-aurora.sh"
echo ""
echo "Live URL (after ~3 min):  https://$BACKEND_DOMAIN"
echo "Health:                   https://$BACKEND_DOMAIN/health"
echo "WebSocket:                wss://$BACKEND_DOMAIN/ws"
