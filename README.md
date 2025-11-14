# EventBridge DLQ Enforcer

AWS Lambda solution that automatically creates and manages Dead Letter Queues (DLQs) for Amazon EventBridge rules. This ensures that failed events are not lost and can be analyzed for troubleshooting.

## Features

- **Automatic DLQ Creation**: Creates SQS dead letter queues for EventBridge rules that don't have them
- **Environment-Aware Naming**: Supports environment prefixes for multi-environment deployments
- **Real-time Enforcement**: Triggers automatically when new targets are added to rules
- **Scheduled Reconciliation**: Periodic checks to ensure all rules have DLQs
- **Orphan Cleanup**: Removes DLQs for deleted rules
- **Dry-run Mode**: Test operations without making changes
- **Flexible Configuration**: Configurable skip lists, schedules, and SQS settings

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   EventBridge   │    │     Lambda      │    │      SQS        │
│     Rules       │───▶│   DLQ Enforcer  │───▶│   DLQ Queues    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        │                       │
        │                       │
        ▼                       ▼
┌─────────────────┐    ┌─────────────────┐
│   CloudTrail    │    │   CloudWatch    │
│   PutTargets    │    │   Scheduled     │
│    Events       │    │     Events      │
└─────────────────┘    └─────────────────┘
```

### How It Works

1. **PutTargets Trigger**: When someone adds/modifies targets on the **monitored EventBridge bus**, CloudTrail logs the API call, which triggers the Lambda
2. **Scheduled Trigger**: Runs periodically (default: every 60 minutes) to ensure consistency
3. **DLQ Creation**: For each rule without a DLQ on the **target EventBridge bus**, creates an SQS queue with appropriate policies
4. **Target Update**: Attaches the DLQ to rule targets that don't already have one
5. **Orphan Cleanup**: Removes DLQs for rules that no longer exist

### Dual-Bus Architecture

The solution supports monitoring one bus while managing DLQs for another:

- **Monitored Bus**: The EventBridge bus whose PutTargets API calls trigger the Lambda
- **Target Bus**: The EventBridge bus whose rules will get DLQs created

**Use Cases:**
- **Same Bus**: Monitor and manage DLQs on the same bus (most common)
- **Cross-Bus**: Monitor a shared/central bus but create DLQs for application-specific buses
- **Multi-Tenant**: Monitor shared infrastructure bus, manage DLQs per tenant bus

## Quick Start

### 1. Deploy Infrastructure

```hcl
# terraform/main.tf
module "eventbridge_dlq_enforcer" {
  source = "./path/to/terraform"

  monitored_event_bus_name = "my-custom-event-bus"  # Bus to monitor for PutTargets
  target_event_bus_name    = "my-custom-event-bus"  # Bus whose rules get DLQs
  environment              = "production"
  env_prefix               = "prod"

  tags = {
    Project = "MyProject"
    Owner   = "DevOps"
  }
}
```

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### 2. Test the Setup

```bash
# Dry run to see what would be created
./scripts/invoke.sh reconcile production dry-run

# Apply changes
./scripts/invoke.sh reconcile production
```

## Configuration

### Terraform Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `monitored_event_bus_name` | EventBridge bus to monitor for PutTargets events | Required |
| `target_event_bus_name` | EventBridge bus whose rules get DLQs created | Required |
| `environment` | Environment name (dev, staging, prod) | Required |
| `env_prefix` | Short environment prefix for queue names | Required |
| `skip_rules` | Comma-separated list of rules to skip | `""` |
| `schedule_enabled` | Enable scheduled reconciliation | `true` |
| `puttargets_trigger_enabled` | Enable real-time PutTargets trigger | `true` |
| `schedule_rate` | Schedule expression | `"rate(60 minutes)"` |

### Environment Variables

The Lambda function supports these environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `EVENT_BUS_NAME` | EventBridge bus name | Required |
| `EVENT_BUS_ARN` | EventBridge bus ARN | Required |
| `ENV_PREFIX` | Environment prefix for DLQ names | `""` |
| `SKIP_RULES` | Comma-separated rules to skip | `""` |
| `DRY_RUN` | Default dry-run mode | `"true"` |
| `SQS_RETENTION_SECONDS` | Message retention period | `"1209600"` (14 days) |
| `SQS_VISIBILITY_TIMEOUT_SECONDS` | Visibility timeout | `"1800"` (30 min) |
| `SQS_SSE_ENABLED` | Enable server-side encryption | `"true"` |

## Usage Examples

### Manual Invocation

```bash
# Reconcile DLQs (dry run)
./scripts/invoke.sh reconcile staging dry-run

# Reconcile DLQs (apply changes)
./scripts/invoke.sh reconcile production

# Clean up DLQs (preserves queues with messages)
./scripts/invoke.sh cleanup staging

# Force clean up all DLQs
./scripts/invoke.sh force-cleanup development dry-run
```

### Direct AWS CLI

```bash
# Dry run reconciliation
aws lambda invoke \
    --function-name eventbridge-dlq-enforcer-prod \
    --payload '{"action": "reconcile", "dryRun": true}' \
    response.json

# Production reconciliation
aws lambda invoke \
    --function-name eventbridge-dlq-enforcer-prod \
    --payload '{"action": "reconcile", "dryRun": false}' \
    response.json

# Cleanup with custom skip rules
aws lambda invoke \
    --function-name eventbridge-dlq-enforcer-prod \
    --payload '{"action": "reconcile", "dryRun": false, "skipRules": ["log-all", "legacy-rule"]}' \
    response.json
```

## DLQ Naming Convention

DLQs are named using the format: `{env-prefix}-{rule-name}-rule-dlq`

**Examples:**
- Rule: `payment-events` → DLQ: `prod-payment-events-rule-dlq`
- Rule: `user-registration` → DLQ: `dev-user-registration-rule-dlq`

**Long Names**: If the combined name exceeds 80 characters, the rule name is truncated to fit within SQS naming limits.

## Advanced Configuration

### Skip Specific Rules

```hcl
module "eventbridge_dlq_enforcer" {
  # ... other config ...
  
  # Skip rules managed by other systems
  skip_rules = "app-log-all,legacy-system-rule,terraform-managed-rule"
}
```

### Custom Schedule

```hcl
module "eventbridge_dlq_enforcer" {
  # ... other config ...
  
  # Run every 6 hours
  schedule_rate = "rate(6 hours)"
  
  # Or use cron expression (daily at 2 AM)
  schedule_rate = "cron(0 2 * * ? *)"
}
```

### Disable Triggers

```hcl
module "eventbridge_dlq_enforcer" {
  # ... other config ...
  
  # Disable real-time triggers (scheduled only)
  puttargets_trigger_enabled = false
  
  # Disable scheduling (manual/real-time only)
  schedule_enabled = false
}
```

## Multi-Environment Setup

### Development
```hcl
module "eventbridge_dlq_enforcer_dev" {
  source = "./terraform"

  event_bus_name = "dev-event-bus"
  environment    = "development"
  env_prefix     = "dev"
  
  # More frequent checks in dev
  schedule_rate = "rate(30 minutes)"
  
  # Disable real-time triggers to reduce noise
  puttargets_trigger_enabled = false
}
```

### Staging
```hcl
module "eventbridge_dlq_enforcer_staging" {
  source = "./terraform"

  event_bus_name = "staging-event-bus"
  environment    = "staging"
  env_prefix     = "stg"
  
  # Skip rules that conflict with testing
  skip_rules = "test-data-generator,mock-service-events"
}
```

### Production
```hcl
module "eventbridge_dlq_enforcer_prod" {
  source = "./terraform"

  event_bus_name = "production-event-bus"
  environment    = "production"
  env_prefix     = "prod"
  
  # Conservative schedule for production
  schedule_rate = "rate(2 hours)"
  
  # Skip critical rules managed elsewhere
  skip_rules = "audit-events,compliance-logging"
}
```

## Monitoring

The solution includes CloudWatch alarms for:

- **Lambda Errors**: Alerts when the function encounters errors
- **High Duration**: Alerts when execution time exceeds 30 seconds

### Custom Monitoring

```hcl
# Add custom alarm actions
resource "aws_sns_topic" "alerts" {
  name = "eventbridge-dlq-alerts"
}

module "eventbridge_dlq_enforcer" {
  # ... other config ...
}

# Override alarm actions
resource "aws_cloudwatch_metric_alarm" "custom_errors" {
  alarm_name          = "eventbridge-dlq-enforcer-errors-custom"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "EventBridge DLQ Enforcer errors"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  
  dimensions = {
    FunctionName = module.eventbridge_dlq_enforcer.lambda_function_name
  }
}
```

## Troubleshooting

### Common Issues

1. **DLQs not being created**
   - Check if rules are being skipped (AWS managed, in skip list)
   - Verify EventBridge bus name matches configuration
   - Run in dry-run mode to see planned operations

2. **Permission errors**
   - Ensure Lambda has necessary IAM permissions
   - Check CloudTrail is enabled for PutTargets trigger

3. **High execution time**
   - Large number of rules can increase processing time
   - Consider increasing Lambda timeout or splitting by bus

### Debug Commands

```bash
# Check what the function would do
./scripts/invoke.sh reconcile prod dry-run

# View recent logs
aws logs describe-log-streams \
    --log-group-name "/aws/lambda/eventbridge-dlq-enforcer-prod" \
    --order-by LastEventTime --descending

# Test with specific rules
aws lambda invoke \
    --function-name eventbridge-dlq-enforcer-prod \
    --payload '{"action": "reconcile", "dryRun": true, "skipRules": []}' \
    response.json
```

## Security Considerations

- **IAM Principle of Least Privilege**: The Lambda only has permissions for required EventBridge and SQS operations
- **Encryption**: SQS queues use server-side encryption by default
- **VPC**: Can be deployed in VPC for additional network isolation
- **Resource Tagging**: All resources are properly tagged for governance

## Contributing

1. **Lambda Code**: Modify `lambda/main.py`
2. **Infrastructure**: Update `terraform/main.tf`
3. **Documentation**: Update this README

### Development Setup

```bash
# Test Lambda code locally
cd lambda
python -m pytest tests/

# Format Terraform code
cd terraform
terraform fmt

# Validate configuration
terraform validate
```

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review CloudWatch logs
3. Test in dry-run mode
4. Open an issue with detailed error messages and configuration