#!/bin/bash

# EventBridge DLQ Enforcer - Lambda Invocation Scripts
# Usage: ./invoke.sh <action> <environment> [dry-run]

set -e

FUNCTION_NAME_PREFIX="eventbridge-dlq-enforcer"
AWS_PROFILE=${AWS_PROFILE:-default}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 <action> <environment> [dry-run]"
    echo ""
    echo "Actions:"
    echo "  reconcile    - Reconcile DLQs for all rules (default)"
    echo "  cleanup      - Delete all DLQs for the event bus"
    echo "  force-cleanup - Delete all DLQs even if they contain messages"
    echo ""
    echo "Examples:"
    echo "  $0 reconcile prod"
    echo "  $0 reconcile staging dry-run"
    echo "  $0 cleanup dev"
    echo "  $0 force-cleanup staging dry-run"
    echo ""
    echo "Environment variables:"
    echo "  AWS_PROFILE - AWS profile to use (default: default)"
    exit 1
}

if [ $# -lt 2 ]; then
    usage
fi

ACTION=$1
ENVIRONMENT=$2
DRY_RUN=${3:-""}

FUNCTION_NAME="${FUNCTION_NAME_PREFIX}-${ENVIRONMENT}"

# Determine if this is a dry run
if [ "$DRY_RUN" = "dry-run" ]; then
    IS_DRY_RUN=true
    echo -e "${YELLOW}🧪 DRY RUN MODE - No changes will be made${NC}"
else
    IS_DRY_RUN=false
    echo -e "${GREEN}🚀 PRODUCTION MODE - Changes will be applied${NC}"
fi

# Build payload based on action
case $ACTION in
    "reconcile")
        PAYLOAD="{\"action\": \"reconcile\", \"dryRun\": $IS_DRY_RUN}"
        echo -e "${BLUE}🔄 Reconciling EventBridge DLQs...${NC}"
        ;;
    "cleanup")
        PAYLOAD="{\"action\": \"delete_all_for_bus\", \"dryRun\": $IS_DRY_RUN, \"forceDelete\": false}"
        echo -e "${YELLOW}🗑️  Cleaning up DLQs (preserving queues with messages)...${NC}"
        ;;
    "force-cleanup")
        PAYLOAD="{\"action\": \"delete_all_for_bus\", \"dryRun\": $IS_DRY_RUN, \"forceDelete\": true}"
        echo -e "${RED}💥 Force cleaning up ALL DLQs (including queues with messages)...${NC}"
        ;;
    *)
        echo -e "${RED}❌ Invalid action: $ACTION${NC}"
        usage
        ;;
esac

echo "Function: $FUNCTION_NAME"
echo "Profile: $AWS_PROFILE"
echo "Payload: $PAYLOAD"
echo ""

# Invoke the Lambda function
echo -e "${BLUE}📡 Invoking Lambda function...${NC}"
aws lambda invoke \
    --function-name "$FUNCTION_NAME" \
    --profile "$AWS_PROFILE" \
    --cli-binary-format raw-in-base64-out \
    --payload "$PAYLOAD" \
    response.json

# Check if invocation was successful
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Lambda invocation successful${NC}"
    echo ""
    echo -e "${BLUE}📊 Response:${NC}"
    python3 -m json.tool response.json
else
    echo -e "${RED}❌ Lambda invocation failed${NC}"
    exit 1
fi

# Cleanup response file
rm -f response.json

echo ""
echo -e "${GREEN}🏁 Complete!${NC}"