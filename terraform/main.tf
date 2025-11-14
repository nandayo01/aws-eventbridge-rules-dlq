# EventBridge DLQ Enforcer Infrastructure

locals {
  target_event_bus_arn = "arn:aws:events:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:event-bus/${var.target_event_bus_name}"
  
  dlq_enforcer_tags = merge(
    {
      CreatedBy   = "Terraform"
      Environment = var.environment
      Service     = "EventBridge"
      ManagedBy   = "eventbridge-dlq-enforcer"
      Purpose     = "EventBridge Rule DLQ"
    },
    var.tags
  )
}

resource "aws_lambda_function" "dlq_enforcer" {
  function_name = "eventbridge-dlq-enforcer-${var.environment}"
  role          = aws_iam_role.dlq_enforcer_role.arn
  handler       = "main.handler"
  runtime       = "python3.12"
  filename      = data.archive_file.dlq_enforcer_zip.output_path
  source_code_hash = data.archive_file.dlq_enforcer_zip.output_base64sha256
  timeout       = 60

  environment {
    variables = {
      EVENT_BUS_NAME                   = var.target_event_bus_name
      EVENT_BUS_ARN                    = local.target_event_bus_arn
      ENV_PREFIX                       = var.env_prefix
      SKIP_RULES                       = var.skip_rules
      TAGS_JSON                        = jsonencode(local.dlq_enforcer_tags)
      SQS_RETENTION_SECONDS            = "1209600"  # 14 days
      SQS_VISIBILITY_TIMEOUT_SECONDS   = "1800"    # 30 minutes
      SQS_MAX_MESSAGE_SIZE             = "262144"   # 256 KB
      SQS_SSE_ENABLED                  = "true"
      ACTION                           = "reconcile"
      DRY_RUN                          = "true"     # Safe default
      FORCE_DELETE                     = "false"
    }
  }

  depends_on = [aws_cloudwatch_log_group.dlq_enforcer]
  tags = local.dlq_enforcer_tags
}

# PutTargets trigger for real-time enforcement
resource "aws_cloudwatch_event_rule" "dlq_enforcer_puttargets" {
  count       = var.puttargets_trigger_enabled ? 1 : 0
  name        = "eventbridge-dlq-enforcer-puttargets-${var.environment}"
  description = "Invoke DLQ enforcer on EventBridge PutTargets for ${var.monitored_event_bus_name}"
  state       = "ENABLED"

  event_pattern = jsonencode({
    "source": ["aws.events"],
    "detail-type": ["AWS API Call via CloudTrail"],
    "detail": {
      "eventSource": ["events.amazonaws.com"],
      "eventName": ["PutTargets"],
      "requestParameters": {
        "eventBusName": [var.monitored_event_bus_name]
      }
    }
  })

  tags = local.dlq_enforcer_tags
}

resource "aws_cloudwatch_event_target" "dlq_enforcer_puttargets_lambda" {
  count     = var.puttargets_trigger_enabled ? 1 : 0
  rule      = aws_cloudwatch_event_rule.dlq_enforcer_puttargets[0].name
  target_id = "lambda"
  arn       = aws_lambda_function.dlq_enforcer.arn
}

# Scheduled trigger for periodic reconciliation
resource "aws_cloudwatch_event_rule" "dlq_enforcer_schedule" {
  count               = var.schedule_enabled ? 1 : 0
  name                = "eventbridge-dlq-enforcer-schedule-${var.environment}"
  description         = "Periodic reconciliation for EventBridge DLQ enforcement"
  schedule_expression = var.schedule_rate
  state               = "ENABLED"
  tags                = local.dlq_enforcer_tags
}

resource "aws_cloudwatch_event_target" "dlq_enforcer_schedule_lambda" {
  count     = var.schedule_enabled ? 1 : 0
  rule      = aws_cloudwatch_event_rule.dlq_enforcer_schedule[0].name
  target_id = "lambda"
  arn       = aws_lambda_function.dlq_enforcer.arn
  
  input = jsonencode({
    "action" = "reconcile"
    "dryRun" = false  # Override for production runs
  })
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "dlq_enforcer" {
  name              = "/aws/lambda/eventbridge-dlq-enforcer-${var.environment}"
  retention_in_days = 14
  tags              = local.dlq_enforcer_tags
}

# CloudWatch Alarms for monitoring
resource "aws_cloudwatch_metric_alarm" "dlq_enforcer_errors" {
  alarm_name          = "eventbridge-dlq-enforcer-errors-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "1"
  alarm_description   = "EventBridge DLQ Enforcer Lambda function errors"
  alarm_actions       = []
  treat_missing_data  = "notBreaching"
  
  dimensions = {
    FunctionName = aws_lambda_function.dlq_enforcer.function_name
  }
  
  tags = local.dlq_enforcer_tags
}

resource "aws_cloudwatch_metric_alarm" "dlq_enforcer_duration" {
  alarm_name          = "eventbridge-dlq-enforcer-duration-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Average"
  threshold           = "30000"  # 30 seconds
  alarm_description   = "EventBridge DLQ Enforcer Lambda function high duration"
  alarm_actions       = []
  treat_missing_data  = "notBreaching"
  
  dimensions = {
    FunctionName = aws_lambda_function.dlq_enforcer.function_name
  }
  
  tags = local.dlq_enforcer_tags
}
