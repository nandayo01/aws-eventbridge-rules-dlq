variable "monitored_event_bus_name" {
  description = "Name of the EventBridge custom bus to monitor the events from to trigger the function"
  type        = string
}

variable "target_event_bus_name" {
  description = "Name of the EventBridge custom bus whose rules will get DLQs created"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod, etc.)"
  type        = string
}

variable "env_prefix" {
  description = "Short environment prefix for queue names (e.g., 'dev', 'stg', 'prod')"
  type        = string
}

variable "skip_rules" {
  description = "Comma-separated list of rule names to skip DLQ enforcement"
  type        = string
  default     = ""
}

variable "schedule_enabled" {
  description = "Enable scheduled reconciliation"
  type        = bool
  default     = true
}

variable "puttargets_trigger_enabled" {
  description = "Enable PutTargets trigger for real-time enforcement"
  type        = bool
  default     = true
}

variable "schedule_rate" {
  description = "Schedule expression for periodic reconciliation"
  type        = string
  default     = "rate(60 minutes)"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}