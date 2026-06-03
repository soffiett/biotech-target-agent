#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# get-url.sh — Print the current public URL of the running container
# Useful after a deploy when the IP wasn't printed, or after a container restart
# ─────────────────────────────────────────────────────────────────────────────
source "$(dirname "$0")/.aws-config"

TASK_ARN=$(aws ecs list-tasks \
    --cluster $APP_NAME \
    --service-name $APP_NAME \
    --region $REGION \
    --query "taskArns[0]" \
    --output text)

if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ]; then
    echo "No running tasks found for service $APP_NAME"
    exit 1
fi

ENI_ID=$(aws ecs describe-tasks \
    --cluster $APP_NAME \
    --tasks $TASK_ARN \
    --region $REGION \
    --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" \
    --output text)

PUBLIC_IP=$(aws ec2 describe-network-interfaces \
    --network-interface-ids $ENI_ID \
    --region $REGION \
    --query "NetworkInterfaces[0].Association.PublicIp" \
    --output text)

echo "App URL: http://$PUBLIC_IP:8501"
