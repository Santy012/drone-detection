import json
import os
from datetime import datetime, timezone
from decimal import Decimal
import boto3

dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

EVENTS_TABLE = os.environ["EVENTS_TABLE"]
DETECTIONS_TABLE = os.environ["DETECTIONS_TABLE"]
NOTIFY_FUNCTION = os.environ["NOTIFY_FUNCTION_NAME"]
EVENT_TIMEOUT_S = 30


def _find_active_event(device_id):
    """Find the most recent ACTIVE event for this device."""
    events_table = dynamodb.Table(EVENTS_TABLE)
    resp = events_table.query(
        KeyConditionExpression="device_id = :did",
        FilterExpression="#s = :active",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":did": device_id,
            ":active": "ACTIVE",
        },
        ScanIndexForward=False,
        Limit=1,
    )
    items = resp.get("Items", [])
    if not items:
        return None

    item = items[0]
    last_det = item.get("last_detection_at", "")
    if last_det:
        last_dt = datetime.fromisoformat(last_det)
        elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
        if elapsed > EVENT_TIMEOUT_S:
            # Close expired event
            events_table.update_item(
                Key={"device_id": device_id, "event_id": item["event_id"]},
                UpdateExpression="SET #s = :ended, ended_at = :now",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":ended": "ENDED",
                    ":now": datetime.now(timezone.utc).isoformat(),
                },
            )
            return None

    return item


def _create_event(device_id, timestamp, max_conf, snapshot_key):
    """Create a new ACTIVE event."""
    events_table = dynamodb.Table(EVENTS_TABLE)
    event_id = f"EVT#{timestamp}"
    events_table.put_item(Item={
        "device_id": device_id,
        "event_id": event_id,
        "status": "ACTIVE",
        "started_at": timestamp,
        "last_detection_at": timestamp,
        "total_detections": 0,
        "max_confidence": Decimal(str(max_conf)),
        "best_snapshot_key": snapshot_key,
        "notifications_sent": 0,
        "last_notification_at": "1970-01-01T00:00:00+00:00",
    })
    return event_id


def _update_event(device_id, event_id, timestamp, num_dets, max_conf, snapshot_key):
    """Update an existing event with new detection data."""
    events_table = dynamodb.Table(EVENTS_TABLE)
    events_table.update_item(
        Key={"device_id": device_id, "event_id": event_id},
        UpdateExpression=(
            "SET last_detection_at = :ts, "
            "total_detections = total_detections + :n, "
            "max_confidence = if_not_exists(max_confidence, :zero)"
        ),
        ExpressionAttributeValues={
            ":ts": timestamp,
            ":n": num_dets,
            ":zero": Decimal("0"),
        },
    )
    # Update best snapshot if this detection has higher confidence
    events_table.update_item(
        Key={"device_id": device_id, "event_id": event_id},
        UpdateExpression="SET max_confidence = :conf, best_snapshot_key = :key",
        ConditionExpression="max_confidence < :conf",
        ExpressionAttributeValues={
            ":conf": Decimal(str(max_conf)),
            ":key": snapshot_key,
        },
    )


def lambda_handler(event, context):
    body = json.loads(event.get("body", "{}"))
    device_id = body["device_id"]
    timestamp = body["timestamp"]
    snapshot_key = body["snapshot_key"]
    dets = body["detections"]

    if not dets:
        return {
            "statusCode": 200,
            "body": json.dumps({"status": "no_detections"}),
        }

    max_conf = max(d["confidence"] for d in dets)

    # Find or create event
    active_event = _find_active_event(device_id)
    if active_event:
        event_id = active_event["event_id"]
    else:
        event_id = _create_event(device_id, timestamp, max_conf, snapshot_key)

    # Update event
    try:
        _update_event(device_id, event_id, timestamp, len(dets), max_conf, snapshot_key)
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        pass  # Current confidence is not higher, that's fine

    # Write individual detections
    detections_table = dynamodb.Table(DETECTIONS_TABLE)
    for det in dets:
        detections_table.put_item(Item={
            "event_id": event_id,
            "timestamp": timestamp,
            "device_id": device_id,
            "snapshot_key": snapshot_key,
            "confidence": Decimal(str(det["confidence"])),
            "bbox_x1": det["x1"],
            "bbox_y1": det["y1"],
            "bbox_x2": det["x2"],
            "bbox_y2": det["y2"],
        })

    # Invoke notify-handler async
    lambda_client.invoke(
        FunctionName=NOTIFY_FUNCTION,
        InvocationType="Event",
        Payload=json.dumps({
            "event_id": event_id,
            "device_id": device_id,
            "snapshot_key": snapshot_key,
            "max_confidence": float(max_conf),
        }),
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"event_id": event_id, "status": "ok"}),
    }
