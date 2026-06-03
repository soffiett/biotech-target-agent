#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh — Build, push, and deploy the app to ECS Fargate
# Run this every time you want to deploy a new version.
#
# Steps:
#   1. Build Docker image (linux/arm64 for Graviton2)
#   2. Push to ECR
#   3. Register new ECS task definition
#   4. Create or update ECS service
#   5. Print the public URL
# ─────────────────────────────────────────────────────────────────────────────
set -e

# Load config saved by setup.sh
CONFIG_FILE="$(dirname "$0")/.aws-config"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: .aws-config not found. Run deploy/setup.sh first."
    exit 1
fi
source "$CONFIG_FILE"

IMAGE_TAG=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")
IMAGE_URI="$ECR_URI:$IMAGE_TAG"
EXECUTION_ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/${APP_NAME}-execution-role"

echo "======================================"
echo "  Biotech Agent — Deploy"
echo "  Image : $IMAGE_URI"
echo "  Region: $REGION"
echo "======================================"

# ── 1. ECR login ──────────────────────────────────────────────────────────────
echo ""
echo "▶ Logging into ECR..."
aws ecr get-login-password --region $REGION | \
    docker login --username AWS --password-stdin \
    "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# ── 2. Build image ────────────────────────────────────────────────────────────
echo ""
echo "▶ Building Docker image (linux/arm64)..."
echo "  This takes ~5 minutes on first build (downloads embedding model)"
cd "$(dirname "$0")/.."
docker build \
    --platform linux/arm64 \
    --tag "$IMAGE_URI" \
    --tag "$ECR_URI:latest" \
    .

# ── 3. Push to ECR ────────────────────────────────────────────────────────────
echo ""
echo "▶ Pushing image to ECR..."
docker push "$IMAGE_URI"
docker push "$ECR_URI:latest"

# ── 4. Register task definition ───────────────────────────────────────────────
echo ""
echo "▶ Registering ECS task definition..."

# Fetch secret ARNs
get_secret_arn() {
    aws secretsmanager describe-secret \
        --secret-id "$APP_NAME/$1" \
        --region $REGION \
        --query "ARN" --output text
}

ANTHROPIC_ARN=$(get_secret_arn "anthropic-api-key")
TAVILY_ARN=$(get_secret_arn "tavily-api-key")
NCBI_ARN=$(get_secret_arn "ncbi-email")

TASK_DEF=$(cat << EOF
{
  "family": "$APP_NAME",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "$EXECUTION_ROLE_ARN",
  "runtimePlatform": {
    "cpuArchitecture": "ARM64",
    "operatingSystemFamily": "LINUX"
  },
  "containerDefinitions": [{
    "name": "$APP_NAME",
    "image": "$IMAGE_URI",
    "essential": true,
    "portMappings": [{
      "containerPort": 8501,
      "protocol": "tcp"
    }],
    "secrets": [
      {"name": "ANTHROPIC_API_KEY", "valueFrom": "$ANTHROPIC_ARN"},
      {"name": "TAVILY_API_KEY",    "valueFrom": "$TAVILY_ARN"},
      {"name": "NCBI_EMAIL",        "valueFrom": "$NCBI_ARN"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/$APP_NAME",
        "awslogs-region": "$REGION",
        "awslogs-stream-prefix": "ecs"
      }
    },
    "healthCheck": {
      "command": ["CMD-SHELL", "curl -f http://localhost:8501/_stcore/health || exit 1"],
      "interval": 30,
      "timeout": 10,
      "retries": 3,
      "startPeriod": 60
    }
  }]
}
EOF
)

TASK_DEF_ARN=$(aws ecs register-task-definition \
    --cli-input-json "$TASK_DEF" \
    --region $REGION \
    --query "taskDefinition.taskDefinitionArn" \
    --output text)

echo "  Task definition: $TASK_DEF_ARN"

# ── 5. Get subnets ────────────────────────────────────────────────────────────
SUBNET_IDS=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=default-for-az,Values=true" \
    --query "Subnets[*].SubnetId" \
    --output text \
    --region $REGION | tr '\t' ',')

echo "  Subnets: $SUBNET_IDS"

# ── 6. Create or update ECS service ──────────────────────────────────────────
echo ""
echo "▶ Deploying to ECS Fargate..."

NETWORK_CONFIG="awsvpcConfiguration={subnets=[$SUBNET_IDS],securityGroups=[$SG_ID],assignPublicIp=ENABLED}"

# Check if service already exists
SERVICE_STATUS=$(aws ecs describe-services \
    --cluster $APP_NAME \
    --services $APP_NAME \
    --region $REGION \
    --query "services[0].status" \
    --output text 2>/dev/null || echo "MISSING")

if [ "$SERVICE_STATUS" = "ACTIVE" ]; then
    echo "  Updating existing service..."
    aws ecs update-service \
        --cluster $APP_NAME \
        --service $APP_NAME \
        --task-definition $TASK_DEF_ARN \
        --region $REGION \
        --force-new-deployment \
        > /dev/null
else
    echo "  Creating new service..."
    aws ecs create-service \
        --cluster $APP_NAME \
        --service-name $APP_NAME \
        --task-definition $TASK_DEF_ARN \
        --desired-count 1 \
        --launch-type FARGATE \
        --network-configuration "$NETWORK_CONFIG" \
        --region $REGION \
        > /dev/null
fi

# ── 7. Wait and get public IP ─────────────────────────────────────────────────
echo ""
echo "▶ Waiting for task to start (up to 3 minutes)..."
sleep 30

for i in {1..10}; do
    TASK_ARN=$(aws ecs list-tasks \
        --cluster $APP_NAME \
        --service-name $APP_NAME \
        --region $REGION \
        --query "taskArns[0]" \
        --output text 2>/dev/null)

    if [ "$TASK_ARN" != "None" ] && [ -n "$TASK_ARN" ]; then
        ENI_ID=$(aws ecs describe-tasks \
            --cluster $APP_NAME \
            --tasks $TASK_ARN \
            --region $REGION \
            --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" \
            --output text 2>/dev/null)

        if [ -n "$ENI_ID" ] && [ "$ENI_ID" != "None" ]; then
            PUBLIC_IP=$(aws ec2 describe-network-interfaces \
                --network-interface-ids $ENI_ID \
                --region $REGION \
                --query "NetworkInterfaces[0].Association.PublicIp" \
                --output text 2>/dev/null)

            if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "None" ]; then
                break
            fi
        fi
    fi
    echo "  Waiting... ($i/10)"
    sleep 15
done

echo ""
echo "======================================"
echo "  Deploy complete!"
echo ""
if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "None" ]; then
    echo "  App URL: http://$PUBLIC_IP:8501"
    echo ""
    echo "  Note: Allow ~60s for the container to finish starting."
    echo "  Logs:  aws logs tail /ecs/$APP_NAME --follow --region $REGION"
else
    echo "  Task is starting — get the URL with:"
    echo "  ./deploy/get-url.sh"
fi
echo "======================================"
