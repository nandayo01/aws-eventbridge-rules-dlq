# Outputs
output "lambda_function_name" {
  description = "Name of the EventBridge DLQ enforcer Lambda function"
  value       = aws_lambda_function.dlq_enforcer.function_name
}

output "lambda_function_arn" {
  description = "ARN of the EventBridge DLQ enforcer Lambda function"
  value       = aws_lambda_function.dlq_enforcer.arn
}

output "puttargets_rule_arn" {
  description = "ARN of the PutTargets EventBridge rule"
  value       = var.puttargets_trigger_enabled ? aws_cloudwatch_event_rule.dlq_enforcer_puttargets[0].arn : null
}

output "schedule_rule_arn" {
  description = "ARN of the scheduled EventBridge rule"
  value       = var.schedule_enabled ? aws_cloudwatch_event_rule.dlq_enforcer_schedule[0].arn : null
}