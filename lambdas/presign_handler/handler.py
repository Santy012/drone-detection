import json
import os
from datetime import datetime, timezone
import boto3

s3 = boto3.client("s3")
BUCKET = os.environ["S3_BUCKET"]
TTL = int(os.environ.get("PRESIGN_TTL", "60"))


def lambda_handler(event, context):
    body = json.loads(event.get("body", "{}"))
    device_id = body.get("device_id", "unknown")

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    ts = str(int(now.timestamp()))

    s3_key = f"annotated/{device_id}/{date_str}/{ts}.jpg"

    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": s3_key, "ContentType": "image/jpeg"},
        ExpiresIn=TTL,
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "upload_url": url,
            "s3_key": s3_key,
            "expires_in": TTL,
        }),
    }
