#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# setup.sh — One-time AWS infrastructure setup
# Run this ONCE before your first deploy.
#
# What it creates:
#   - ECR repository (stores Docker images)
#   - ECS cluster (runs containers)
#   - IAM task execution role (allows ECS to pull images + read secrets)
#   - CloudWatch log group (container logs)
#   - Security group (opens port 8501)
#   - Secrets Manager entries (API keys)
# ─────────────────────────────────────────────────────────────────────────────
set -e  # exit on any error

REGION=us-west-1
APP_NAME=biotech-target-agent
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "======================================"
echo "  Biotech Agent — AWS Setup"
echo "  Account : $ACCOUNT_ID"
echo "  Region  : $REGION"
echo "======================================"

# ── 1. ECR repository ─────────────────────────────────────────────────────────
echo ""
echo "▶ Creating ECR repository..."
aws ecr create-repository \
    --repository-name $APP_NAME \
    --region $REGION \
    --image-scanning-configuration scanOnPush=true \
    2>/dev/null || echo "  ECR repo already exists — skipping"

ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$APP_NAME"
echo "  ECR URI: $ECR_URI"

# ── 2. ECS cluster ────────────────────────────────────────────────────────────
echo ""
echo "▶ Creating ECS cluster..."
aws ecs create-cluster \
    --cluster-name $APP_NAME \
    --region $REGION \
    2>/dev/null || echo "  Cluster already exists — skipping"

# ── 3. IAM task execution role ────────────────────────────────────────────────
echo ""
echo "▶ Creating IAM task execution role..."

# Trust policy — allows ECS tasks to assume this role
cat > /tmp/ecs-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "ecs-tasks.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
    --role-name ${APP_NAME}-execution-role \
    --assume-role-policy-document file:///tmp/ecs-trust-policy.json \
    2>/dev/null || echo "  IAM role already exists — skipping"

# Attach standard ECS execution policy (pull from ECR, write to CloudWatch)
aws iam attach-role-policy \
    --role-name ${APP_NAME}-execution-role \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy \
    2>/dev/null || true

# Add Secrets Manager read access
cat > /tmp/secrets-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ],
    "Resource": "arn:aws:secretsmanager:$REGION:$ACCOUNT_ID:secret:$APP_NAME/*"
  }]
}
EOF

aws iam put-role-policy \
    --role-name ${APP_NAME}-execution-role \
    --policy-name ${APP_NAME}-secrets-policy \
    --policy-document file:///tmp/secrets-policy.json

echo "  IAM role configured"

# ── 4. CloudWatch log group ───────────────────────────────────────────────────
echo ""
echo "▶ Creating CloudWatch log group..."
aws logs create-log-group \
    --log-group-name /ecs/$APP_NAME \
    --region $REGION \
    2>/dev/null || echo "  Log group already exists — skipping"

aws logs put-retention-policy \
    --log-group-name /ecs/$APP_NAME \
    --retention-in-days 7 \
    --region $REGION

# ── 5. Security group ─────────────────────────────────────────────────────────
echo ""
echo "▶ Creating security group..."

VPC_ID=$(aws ec2 describe-vpcs \
    --filters "Name=is-default,Values=true" \
    --query "Vpcs[0].VpcId" \
    --output text \
    --region $REGION)

echo "  Using default VPC: $VPC_ID"

SG_ID=$(aws ec2 create-security-group \
    --group-name ${APP_NAME}-sg \
    --description "Biotech Target Agent — allow port 8501" \
    --vpc-id $VPC_ID \
    --region $REGION \
    --query "GroupId" \
    --output text \
    2>/dev/null) || \
SG_ID=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=${APP_NAME}-sg" \
    --query "SecurityGroups[0].GroupId" \
    --output text \
    --region $REGION)

# Open port 8501 to the world
aws ec2 authorize-security-group-ingress \
    --group-id $SG_ID \
    --protocol tcp \
    --port 8501 \
    --cidr 0.0.0.0/0 \
    --region $REGION \
    2>/dev/null || echo "  Port 8501 rule already exists — skipping"

echo "  Security group: $SG_ID"

# ── 6. Secrets Manager ────────────────────────────────────────────────────────
echo ""
echo "▶ Storing API keys in Secrets Manager..."
echo "  (Loading from your local .env file)"

# Load from local .env
if [ -f ../.env ]; then
    export $(grep -v '^#' ../.env | xargs)
elif [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
else
    echo "  ERROR: .env file not found. Please run from the project root."
    exit 1
fi

store_secret() {
    local name=$1
    local value=$2
    aws secretsmanager create-secret \
        --name "$APP_NAME/$name" \
        --secret-string "$value" \
        --region $REGION \
        2>/dev/null || \
    aws secretsmanager put-secret-value \
        --secret-id "$APP_NAME/$name" \
        --secret-string "$value" \
        --region $REGION
    echo "  Stored: $APP_NAME/$name"
}

store_secret "anthropic-api-key" "$ANTHROPIC_API_KEY"
store_secret "tavily-api-key"    "$TAVILY_API_KEY"
store_secret "ncbi-email"        "$NCBI_EMAIL"

# ── 7. Save config for deploy.sh ──────────────────────────────────────────────
cat > deploy/.aws-config << EOF
REGION=$REGION
APP_NAME=$APP_NAME
ACCOUNT_ID=$ACCOUNT_ID
ECR_URI=$ECR_URI
VPC_ID=$VPC_ID
SG_ID=$SG_ID
EOF

echo ""
echo "======================================"
echo "  Setup complete!"
echo "  Config saved to deploy/.aws-config"
echo ""
echo "  Next step: run  ./deploy/deploy.sh"
echo "======================================"
