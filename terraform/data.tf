
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "archive_file" "dlq_enforcer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda"
  output_path = "${path.module}/eventbridge-dlq-enforcer.zip"
}

data "aws_iam_policy_document" "dlq_enforcer_assume" {
  statement {
    effect = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "dlq_enforcer_inline" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "events:ListRules",
      "events:ListTargetsByRule",
      "events:DescribeRule",
      "events:PutTargets"
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "sqs:CreateQueue",
      "sqs:GetQueueUrl",
      "sqs:GetQueueAttributes",
      "sqs:SetQueueAttributes",
      "sqs:TagQueue",
      "sqs:DeleteQueue",
      "sqs:ListQueues"
    ]
    resources = ["*"]
  }
}