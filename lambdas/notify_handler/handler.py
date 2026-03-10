import json
import os
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.parse import urlencode
import boto3
import io

dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

EVENTS_TABLE = os.environ["EVENTS_TABLE"]
BUCKET = os.environ["S3_BUCKET"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
COOLDOWN = int(os.environ.get("COOLDOWN_SECONDS", "30"))
MAX_NOTIF = int(os.environ.get("MAX_NOTIFICATIONS", "10"))

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def _send_telegram_photo(image_bytes, caption):
    """Send photo to Telegram using multipart/form-data with urllib."""
    boundary = "----DroneDetectionBoundary"
    body = io.BytesIO()

    # caption field
    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="chat_id"\r\n\r\n')
    body.write(f"{CHAT_ID}\r\n".encode())

    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="caption"\r\n\r\n')
    body.write(f"{caption}\r\n".encode())

    # photo field
    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="photo"; filename="snapshot.jpg"\r\n')
    body.write(b"Content-Type: image/jpeg\r\n\r\n")
    body.write(image_bytes)
    body.write(b"\r\n")

    body.write(f"--{boundary}--\r\n".encode())

    content_type = f"multipart/form-data; boundary={boundary}"
    data = body.getvalue()

    req = Request(
        f"{TELEGRAM_API}/sendPhoto",
        data=data,
        headers={"Content-Type": content_type},
        method="POST",
    )
    resp = urlopen(req, timeout=10)
    return json.loads(resp.read())


def _send_telegram_text(text):
    """Send text message to Telegram (fallback when no image available)."""
    data = urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    req = Request(f"{TELEGRAM_API}/sendMessage", data=data, method="POST")
    resp = urlopen(req, timeout=10)
    return json.loads(resp.read())


def lambda_handler(event, context):
    event_id = event["event_id"]
    device_id = event["device_id"]
    snapshot_key = event["snapshot_key"]
    max_confidence = event.get("max_confidence", 0)

    # Read event state
    events_table = dynamodb.Table(EVENTS_TABLE)
    resp = events_table.get_item(
        Key={"device_id": device_id, "event_id": event_id}
    )
    ev = resp.get("Item")
    if not ev:
        print(f"Event not found: {device_id}/{event_id}")
        return {"status": "event_not_found"}

    # Check cooldown
    now = datetime.now(timezone.utc)
    last_notif_str = ev.get("last_notification_at", "1970-01-01T00:00:00+00:00")
    last_notif = datetime.fromisoformat(last_notif_str)
    elapsed = (now - last_notif).total_seconds()

    if elapsed < COOLDOWN:
        print(f"Cooldown active: {elapsed:.0f}s < {COOLDOWN}s")
        return {"status": "cooldown"}

    # Check notification limit
    sent = int(ev.get("notifications_sent", 0))
    if sent >= MAX_NOTIF:
        print(f"Max notifications reached: {sent}/{MAX_NOTIF}")
        return {"status": "max_reached"}

    # Build caption
    total_dets = int(ev.get("total_detections", 0))
    caption = (
        f"🚁 Drone detectado!\n"
        f"Confianza: {max_confidence:.0%}\n"
        f"Detecciones en evento: {total_dets}\n"
        f"Dispositivo: {device_id}\n"
        f"Evento: {event_id}"
    )

    # Download annotated image from S3 and send to Telegram
    image_bytes = None
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=snapshot_key)
        image_bytes = obj["Body"].read()
    except Exception as e:
        print(f"Failed to download image: {e}")

    try:
        if image_bytes:
            _send_telegram_photo(image_bytes, caption)
        else:
            _send_telegram_text(caption)
        print(f"Telegram notification sent ({sent + 1}/{MAX_NOTIF})")
    except Exception as e:
        print(f"Telegram send failed: {e}")
        return {"status": "telegram_error"}

    # Update event
    events_table.update_item(
        Key={"device_id": device_id, "event_id": event_id},
        UpdateExpression="SET last_notification_at = :now ADD notifications_sent :one",
        ExpressionAttributeValues={
            ":now": now.isoformat(),
            ":one": 1,
        },
    )

    return {"status": "notified"}
