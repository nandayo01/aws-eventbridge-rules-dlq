import json
import os
import hashlib
import logging
from typing import Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

# Configure logging for Lambda
logger = logging.getLogger()
if logger.hasHandlers():
    logger.setLevel(logging.INFO)
else:
    logging.basicConfig(level=logging.INFO)

EVENTS = boto3.client("events")
SQS = boto3.client("sqs")


def get_env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def get_rule_arn(rule_name: str, bus_arn: str) -> str:
    parts = bus_arn.split(":")
    region = parts[3]
    account_id = parts[4]
    bus_name = bus_arn.split("/")[-1]
    return f"arn:aws:events:{region}:{account_id}:rule/{bus_name}/{rule_name}"


def generate_dlq_name(rule_name: str, env_prefix: str = "") -> str:
    """Generate DLQ name with format: {env-prefix}-{rule-name}-rule-dlq"""
    suffix = "-rule-dlq"  # 9 characters
    
    if env_prefix:
        # Calculate available space for rule_name
        prefix_with_dash = f"{env_prefix}-"  # env + dash
        max_rule_len = 80 - len(prefix_with_dash) - len(suffix)
        
        # Truncate rule_name if needed
        if len(rule_name) > max_rule_len:
            rule_name = rule_name[:max_rule_len]
        
        return f"{prefix_with_dash}{rule_name}{suffix}"
    else:
        # No env prefix case
        max_rule_len = 80 - len(suffix)
        if len(rule_name) > max_rule_len:
            rule_name = rule_name[:max_rule_len]
        
        return f"{rule_name}{suffix}"


def list_all_rules(event_bus_name: str) -> List[Dict]:
    rules: List[Dict] = []
    next_token: Optional[str] = None
    while True:
        kwargs = {"EventBusName": event_bus_name}
        if next_token:
            kwargs["NextToken"] = next_token
        resp = EVENTS.list_rules(**kwargs)
        rules.extend(resp.get("Rules", []))
        next_token = resp.get("NextToken")
        if not next_token:
            break
    return rules


def list_targets(rule_name: str, event_bus_name: str) -> List[Dict]:
    targets: List[Dict] = []
    next_token: Optional[str] = None
    while True:
        kwargs = {"Rule": rule_name, "EventBusName": event_bus_name}
        if next_token:
            kwargs["NextToken"] = next_token
        resp = EVENTS.list_targets_by_rule(**kwargs)
        targets.extend(resp.get("Targets", []))
        next_token = resp.get("NextToken")
        if not next_token:
            break
    return targets


def get_queue_by_name(name: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        q_url = SQS.get_queue_url(QueueName=name)["QueueUrl"]
        attrs = SQS.get_queue_attributes(QueueUrl=q_url, AttributeNames=["QueueArn"])["Attributes"]
        return q_url, attrs["QueueArn"]
    except ClientError as e:
        if e.response["Error"]["Code"] in ("AWS.SimpleQueueService.NonExistentQueue", "QueueDoesNotExist"):
            return None, None
        raise


def list_all_dlq_queues() -> List[Dict]:
    """List all DLQ queues in the account"""
    queues = []
    try:
        resp = SQS.list_queues()
        queue_urls = resp.get("QueueUrls", [])
        
        for url in queue_urls:
            queue_name = url.split("/")[-1]
            if "-rule-dlq" in queue_name:
                # Extract rule name from format: env-rule-name-rule-dlq
                if queue_name.count("-") >= 3:
                    parts = queue_name.split("-")
                    # Find -rule-dlq suffix and extract everything before it
                    rule_dlq_index = -1
                    for i in range(len(parts) - 2):
                        if parts[i] == "rule" and parts[i + 1] == "dlq":
                            rule_dlq_index = i
                            break
                    if rule_dlq_index > 0:
                        # Skip env prefix (first part) and take until rule-dlq
                        rule_name = "-".join(parts[1:rule_dlq_index])
                        queues.append({
                            "name": queue_name,
                            "url": url,
                            "rule_name": rule_name
                        })
    except ClientError:
        pass
    return queues


def rule_has_dlq_attached(rule_name: str, event_bus_name: str) -> bool:
    """Check if rule already has DLQ attached to any target and the queue actually exists"""
    try:
        targets = list_targets(rule_name, event_bus_name)
        for target in targets:
            if target.get("DeadLetterConfig") and target["DeadLetterConfig"].get("Arn"):
                # Check if the DLQ queue actually exists
                dlq_arn = target["DeadLetterConfig"]["Arn"]
                queue_name = dlq_arn.split(":")[-1]
                q_url, q_arn = get_queue_by_name(queue_name)
                if q_url is not None:
                    return True
        return False
    except ClientError:
        return False


def ensure_queue_and_policy(rule_name: str, dlq_name: str, tags: Dict[str, str], settings: Dict[str, str], 
                           event_bus_arn: str, dry_run: bool, event_bus_name: str) -> Dict[str, any]:
    """Create queue and policy if needed, return operation details"""
    result = {
        "rule_name": rule_name,
        "dlq_name": dlq_name,
        "queue_created": False,
        "policy_updated": False,
        "targets_updated": 0,
        "status": "skipped",
        "reason": ""
    }
    
    if dry_run:
        # In dry-run mode, simulate operations without AWS API calls
        result["queue_created"] = True
        result["policy_updated"] = True
        result["targets_updated"] = 1
        result["status"] = "would_create"
        logger.info(f"[DRY] {rule_name} -> {dlq_name}")
        return result
    
    # Check if rule already has DLQ
    if rule_has_dlq_attached(rule_name, event_bus_name):
        result["status"] = "skipped"
        result["reason"] = "dlq_exists"
        return result
    
    # Create queue if needed
    q_url, q_arn = get_queue_by_name(dlq_name)
    if q_url is None:
        attributes = {
            "MessageRetentionPeriod": str(settings["message_retention_seconds"]),
            "VisibilityTimeout": str(settings["visibility_timeout_seconds"]),
            "MaximumMessageSize": str(settings["max_message_size"]),
            "SqsManagedSseEnabled": "true" if settings["sse_enabled"] else "false",
        }
        resp = SQS.create_queue(QueueName=dlq_name, Attributes=attributes, tags=tags)
        q_url = resp["QueueUrl"]
        attrs = SQS.get_queue_attributes(QueueUrl=q_url, AttributeNames=["QueueArn"])["Attributes"]
        q_arn = attrs["QueueArn"]
        result["queue_created"] = True
        logger.info(f"✅ Created: {rule_name} -> {dlq_name}")
    else:
        logger.info(f"📋 Exists: {rule_name} -> {dlq_name}")
    
    # Update policy
    rule_arn = get_rule_arn(rule_name, event_bus_arn)
    if update_queue_policy(q_url, q_arn, rule_arn):
        result["policy_updated"] = True
    
    # Attach to targets
    targets_updated = attach_dlq_to_targets(rule_name, event_bus_name, q_arn)
    result["targets_updated"] = targets_updated
    
    if result["queue_created"] or result["targets_updated"] > 0:
        result["status"] = "updated"
    else:
        result["status"] = "no_change"
    
    return result


def update_queue_policy(queue_url: str, queue_arn: str, rule_arn: str) -> bool:
    """Update SQS policy to allow EventBridge"""
    try:
        desired_statement = {
            "Sid": f"AllowEventBridgeSend-{rule_arn.split('/')[-1]}",
            "Effect": "Allow",
            "Principal": {"Service": "events.amazonaws.com"},
            "Action": "sqs:SendMessage",
            "Resource": queue_arn,
            "Condition": {"ArnEquals": {"aws:SourceArn": rule_arn}},
        }
        
        # Get existing policy
        try:
            resp = SQS.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["Policy"])
            existing_policy_str = resp.get("Attributes", {}).get("Policy")
            if existing_policy_str:
                policy = json.loads(existing_policy_str)
            else:
                policy = {"Version": "2012-10-17", "Statement": []}
        except (ClientError, json.JSONDecodeError):
            policy = {"Version": "2012-10-17", "Statement": []}
        
        statements = policy.get("Statement", [])
        
        # Check if statement already exists
        for st in statements:
            if (st.get("Principal", {}).get("Service") == "events.amazonaws.com"
                and st.get("Action") == "sqs:SendMessage"
                and st.get("Condition", {}).get("ArnEquals", {}).get("aws:SourceArn") == rule_arn):
                return False  # Already exists
        
        # Add new statement
        statements.append(desired_statement)
        policy["Statement"] = statements
        SQS.set_queue_attributes(QueueUrl=queue_url, Attributes={"Policy": json.dumps(policy)})
        return True
    except ClientError:
        return False


def attach_dlq_to_targets(rule_name: str, event_bus_name: str, queue_arn: str) -> int:
    """Attach DLQ to targets that don't have one"""
    try:
        targets = list_targets(rule_name, event_bus_name)
        to_update = []
        
        for t in targets:
            target_arn = t.get("Arn", "")
            if not target_arn or target_arn == "arn:aws:events:::" or ":archive/" in target_arn:
                continue
            if t.get("DeadLetterConfig") and t["DeadLetterConfig"].get("Arn"):
                continue
            
            # Clone and add DLQ
            clone = {"Id": t["Id"], "Arn": t["Arn"]}
            for key in ("RoleArn", "Input", "InputPath", "InputTransformer", "KinesisParameters",
                       "RunCommandParameters", "EcsParameters", "BatchParameters", "SqsParameters",
                       "HttpParameters", "RedshiftDataParameters", "RetryPolicy"):
                if key in t:
                    clone[key] = t[key]
            clone["DeadLetterConfig"] = {"Arn": queue_arn}
            to_update.append(clone)
        
        if to_update:
            EVENTS.put_targets(Rule=rule_name, EventBusName=event_bus_name, Targets=to_update)
            
        return len(to_update)
    except ClientError:
        return 0


def cleanup_orphaned_dlqs(rules: List[Dict], dry_run: bool) -> Dict[str, any]:
    """Clean up DLQ queues that have no corresponding rule"""
    result = {"orphaned_queues": [], "deleted_count": 0}
    
    if dry_run:
        # In dry-run mode, don't make AWS API calls to list queues
        # Just return empty result since we can't check without API calls
        return result
    
    # Get all rule names
    rule_names = set()
    for rule in rules:
        if not (rule.get("ManagedBy") and "aws" in rule.get("ManagedBy", "").lower()):
            rule_names.add(rule["Name"])
    
    # Get all DLQ queues
    dlq_queues = list_all_dlq_queues()
    
    for queue in dlq_queues:
        # Use the rule_name that was already extracted in list_all_dlq_queues
        potential_rule = queue["rule_name"]
        
        if potential_rule not in rule_names:
            result["orphaned_queues"].append({
                "queue_name": queue["name"],
                "rule_name": potential_rule,
                "action": "would_delete" if dry_run else "deleted"
            })
            
            if dry_run:
                logger.info(f"[DRY] Would delete orphaned: {queue['name']}")
            else:
                try:
                    SQS.delete_queue(QueueUrl=queue["url"])
                    result["deleted_count"] += 1
                    logger.info(f"🗑️ Deleted orphaned: {queue['name']}")
                except ClientError as e:
                    logger.warning(f"Failed to delete {queue['name']}: {e}")
    
    return result


def reconcile_bus(event_bus_name: str, event_bus_arn: str, tags: Dict[str, str], settings: Dict[str, str], dry_run: bool, env_prefix: str = "", skip_rules: List[str] = None) -> Dict[str, any]:
    """Main reconciliation logic"""
    logger.info(f"🔄 Reconciling {event_bus_name} (dry_run={dry_run})")
    
    if skip_rules is None:
        skip_rules = []
    
    rules = list_all_rules(event_bus_name)
    operations = []
    
    created = 0
    policies = 0
    attached = 0
    skipped = 0
    
    for rule in rules:
        rule_name = rule["Name"]
        managed_by = rule.get("ManagedBy", "")
        
        # Skip AWS managed rules
        if managed_by and "aws" in managed_by.lower():
            skipped += 1
            continue
        
        # Skip explicitly configured rules (configurable)
        if rule_name in skip_rules:
            logger.debug(f"Skipping configured rule: {rule_name}")
            skipped += 1
            continue
        
        dlq_name = generate_dlq_name(rule_name, env_prefix)
        operation = ensure_queue_and_policy(rule_name, dlq_name, tags, settings, event_bus_arn, dry_run, event_bus_name)
        operations.append(operation)
        
        if operation["queue_created"]:
            created += 1
        if operation["policy_updated"]:
            policies += 1
        if operation["targets_updated"] > 0:
            attached += operation["targets_updated"]
    
    # Clean up orphaned DLQs
    orphan_cleanup = cleanup_orphaned_dlqs(rules, dry_run)
    
    result = {
        "queues_created": created,
        "policies_updated": policies,
        "targets_attached": attached,
        "rules_total": len(rules),
        "rules_skipped": skipped,
        "operations": operations,
        "orphaned_cleanup": orphan_cleanup
    }
    
    logger.info(f"✅ Complete: {created} created, {attached} attached, {skipped} skipped, {len(orphan_cleanup['orphaned_queues'])} orphaned")
    return result


def cleanup_all_dlqs(event_bus_name: str, dry_run: bool, force_delete: bool, env_prefix: str = "", skip_rules: List[str] = None) -> Dict[str, any]:
    """Delete all DLQ queues for the bus"""
    logger.info(f"🗑️ Cleaning up all DLQs (dry_run={dry_run}, force={force_delete})")
    
    if skip_rules is None:
        skip_rules = []
    
    rules = list_all_rules(event_bus_name)
    deleted_queues = []
    deleted_count = 0
    
    for rule in rules:
        rule_name = rule["Name"]
        managed_by = rule.get("ManagedBy", "")
        
        if managed_by and "aws" in managed_by.lower():
            continue
        
        # Skip explicitly configured rules (configurable)
        if rule_name in skip_rules:
            logger.debug(f"Skipping configured rule during cleanup: {rule_name}")
            continue
        
        dlq_name = generate_dlq_name(rule_name, env_prefix)
        
        if dry_run:
            q_url, q_arn = get_queue_by_name(dlq_name)
            if q_url:
                deleted_queues.append({"rule_name": rule_name, "dlq_name": dlq_name, "action": "would_delete"})
                logger.info(f"[DRY] Would delete: {dlq_name}")
        else:
            try:
                q_url, q_arn = get_queue_by_name(dlq_name)
                if q_url:
                    # Check for messages if not forcing
                    if not force_delete:
                        try:
                            attrs = SQS.get_queue_attributes(
                                QueueUrl=q_url, 
                                AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"]
                            )["Attributes"]
                            msg_count = int(attrs.get("ApproximateNumberOfMessages", "0")) + int(attrs.get("ApproximateNumberOfMessagesNotVisible", "0"))
                            if msg_count > 0:
                                logger.warning(f"⚠️ Skipping {dlq_name} - has {msg_count} messages (use forceDelete=true)")
                                continue
                        except ClientError:
                            pass
                    
                    # Detach from targets first
                    targets = list_targets(rule_name, event_bus_name)
                    to_update = []
                    for t in targets:
                        if t.get("DeadLetterConfig") and t["DeadLetterConfig"].get("Arn") == q_arn:
                            clone = {"Id": t["Id"], "Arn": t["Arn"]}
                            for key in ("RoleArn", "Input", "InputPath", "InputTransformer", "KinesisParameters",
                                       "RunCommandParameters", "EcsParameters", "BatchParameters", "SqsParameters",
                                       "HttpParameters", "RedshiftDataParameters", "RetryPolicy"):
                                if key in t:
                                    clone[key] = t[key]
                            to_update.append(clone)
                    
                    if to_update:
                        EVENTS.put_targets(Rule=rule_name, EventBusName=event_bus_name, Targets=to_update)
                    
                    # Delete queue
                    SQS.delete_queue(QueueUrl=q_url)
                    deleted_queues.append({"rule_name": rule_name, "dlq_name": dlq_name, "action": "deleted"})
                    deleted_count += 1
                    logger.info(f"🗑️ Deleted: {dlq_name}")
                    
            except ClientError as e:
                logger.warning(f"Failed to delete {dlq_name}: {e}")
    
    result = {
        "deleted_count": deleted_count,
        "deleted_queues": deleted_queues,
        "rules_processed": len([r for r in rules if not (r.get("ManagedBy") and "aws" in r.get("ManagedBy", "").lower())])
    }
    
    logger.info(f"✅ Cleanup complete: {deleted_count} deleted")
    return result


def handler(event, context):
    logger.info(f"🚀 Start - Request: {context.aws_request_id}")
    
    event_bus_name = os.environ["EVENT_BUS_NAME"]
    event_bus_arn = os.environ["EVENT_BUS_ARN"]
    env_prefix = os.getenv("ENV_PREFIX", "")
    dry_run = get_env_bool("DRY_RUN", False)
    action = os.getenv("ACTION", "reconcile")
    force_delete = get_env_bool("FORCE_DELETE", False)
    
    # Parse skip rules from environment
    skip_rules_str = os.getenv("SKIP_RULES", "")
    skip_rules = [rule.strip() for rule in skip_rules_str.split(",") if rule.strip()] if skip_rules_str else []
    
    # Override from payload
    if isinstance(event, dict):
        action = event.get("action", action)
        if "dryRun" in event:
            dry_run = bool(event.get("dryRun"))
        if "forceDelete" in event:
            force_delete = bool(event.get("forceDelete"))
        if "skipRules" in event:
            skip_rules = event.get("skipRules", skip_rules)
    
    # Settings
    tags_env = os.getenv("TAGS_JSON", "{}")
    try:
        tags = json.loads(tags_env)
    except Exception:
        tags = {}
    
    settings = {
        "message_retention_seconds": int(os.getenv("SQS_RETENTION_SECONDS", "1209600")),
        "visibility_timeout_seconds": int(os.getenv("SQS_VISIBILITY_TIMEOUT_SECONDS", "1800")),
        "max_message_size": int(os.getenv("SQS_MAX_MESSAGE_SIZE", "262144")),
        "sse_enabled": get_env_bool("SQS_SSE_ENABLED", True),
    }
    
    if action == "delete_all_for_bus":
        result = cleanup_all_dlqs(event_bus_name, dry_run=dry_run, force_delete=force_delete, env_prefix=env_prefix, skip_rules=skip_rules)
        response = {"action": action, "result": result, "dry_run": dry_run}
    else:
        result = reconcile_bus(event_bus_name, event_bus_arn, tags, settings, dry_run=dry_run, env_prefix=env_prefix, skip_rules=skip_rules)
        response = {"action": "reconcile", "result": result, "dry_run": dry_run}
    
    logger.info(f"🏁 Complete")
    return response