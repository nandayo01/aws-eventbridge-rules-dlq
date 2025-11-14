# Basic usage example - same bus for monitoring and DLQ creation
module "eventbridge_dlq_enforcer" {
  source = "../"

  monitored_event_bus_name = "my-custom-event-bus"
  target_event_bus_name    = "my-custom-event-bus"
  environment              = "production"
  env_prefix               = "prod"

  tags = {
    Project = "MyProject"
    Owner   = "DevOps"
  }
}

# Cross-bus example - monitor one bus, create DLQs for another
module "eventbridge_dlq_enforcer_cross_bus" {
  source = "../"

  monitored_event_bus_name = "shared-event-bus"      # Watch this bus for PutTargets
  target_event_bus_name    = "application-event-bus" # Create DLQs for rules on this bus
  environment              = "staging"
  env_prefix               = "stg"
  
  # Skip specific rules that are managed elsewhere
  skip_rules = "log-all-events,legacy-rule-1"
  
  # Custom schedule - run every 2 hours
  schedule_rate = "rate(2 hours)"
  
  # Disable real-time triggers for staging
  puttargets_trigger_enabled = false

  tags = {
    Project     = "MyProject"
    Environment = "staging"
    Owner       = "DevOps"
  }
}