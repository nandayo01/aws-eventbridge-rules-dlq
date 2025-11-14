resource "aws_iam_role" "dlq_enforcer_role" {
  name               = "eventbridge-dlq-enforcer-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.dlq_enforcer_assume.json
  tags               = local.dlq_enforcer_tags
}

resource "aws_iam_role_policy" "dlq_enforcer_policy" {
  name   = "eventbridge-dlq-enforcer-inline"
  role   = aws_iam_role.dlq_enforcer_role.id
  policy = data.aws_iam_policy_document.dlq_enforcer_inline.json
}

resource "aws_lambda_permission" "allow_events_puttargets" {
  count         = var.puttargets_trigger_enabled ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridgePutTargets"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dlq_enforcer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.dlq_enforcer_puttargets[0].arn
}

resource "aws_lambda_permission" "allow_events_schedule" {
  count         = var.schedule_enabled ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridgeSchedule"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dlq_enforcer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.dlq_enforcer_schedule[0].arn
}