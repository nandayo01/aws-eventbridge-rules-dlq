# Changelog

All notable changes to the EventBridge DLQ Enforcer project will be documented in this file.

## [1.0.0] - 2025-11-14

### Added
- **Initial release** of EventBridge DLQ Enforcer
- **Automatic DLQ creation** for EventBridge rules without dead letter queues
- **Environment-aware naming** with configurable prefixes
- **Real-time enforcement** via CloudTrail PutTargets events
- **Scheduled reconciliation** with configurable intervals
- **Dry-run mode** for safe testing and validation
- **Orphan cleanup** to remove DLQs for deleted rules
- **Flexible skip rules** configuration
- **Comprehensive Terraform module** with examples
- **CLI scripts** for easy manual invocation
- **CloudWatch monitoring** with error and duration alarms
- **Multi-environment support** with proper resource naming

### Features
- Environment-prefixed DLQ naming: `{env-prefix}-{rule-name}-rule-dlq`
- Automatic SQS queue policy creation for EventBridge access
- Smart name truncation for long rule names (80 character limit)
- Configurable SQS settings (retention, visibility timeout, encryption)
- Comprehensive logging with emojis for better visibility

### Infrastructure
- Lambda function with proper IAM roles and policies
- EventBridge rules for real-time and scheduled triggers
- CloudWatch log groups with configurable retention
- CloudWatch alarms for error monitoring
- Terraform module with input validation and outputs

### Documentation
- Complete README with usage examples
- Terraform examples for different environments
- Troubleshooting guide and best practices
- Architecture diagrams and flow explanations