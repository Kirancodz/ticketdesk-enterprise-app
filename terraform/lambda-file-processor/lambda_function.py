import json
import logging
import os
import re
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

EXPECTED_BUCKET = os.environ.get(
    "ATTACHMENT_BUCKET",
    "ticketdesk-poc-attachments-635476133762-ap-south-1"
)

ATTACHMENT_PATTERN = re.compile(
    r"TicketLogs/Tickets/(TKT-[0-9]{4}-[0-9]{4,})/Attachments/([^/]+)"
)


def get_created_objects(event):
    # EventBridge S3 Object Created event
    if (
        event.get("source") == "aws.s3"
        and event.get("detail-type") == "Object Created"
    ):
        detail = event["detail"]

        yield (
            detail["bucket"]["name"],
            unquote_plus(detail["object"]["key"])
        )

    # Existing S3 notification event format
    for record in event.get("Records", []):
        if record.get("eventSource") != "aws:s3":
            continue

        if not record.get("eventName", "").startswith("ObjectCreated:"):
            continue

        yield (
            record["s3"]["bucket"]["name"],
            unquote_plus(record["s3"]["object"]["key"])
        )


def lambda_handler(event, context):
    processed = []

    for bucket, object_key in get_created_objects(event):

        if bucket != EXPECTED_BUCKET:
            raise ValueError("Unexpected S3 bucket")

        match = ATTACHMENT_PATTERN.fullmatch(object_key)

        if not match:
            logger.info("Skipping non-attachment object")
            continue

        ticket_id = match.group(1)

        metadata = s3.head_object(
            Bucket=bucket,
            Key=object_key
        )

        result = {
            "ticket_id": ticket_id,
            "bucket": bucket,
            "object_key": object_key,
            "file_size_bytes": metadata["ContentLength"],
            "content_type": metadata.get(
                "ContentType",
                "application/octet-stream"
            ),
            "status": "METADATA_VERIFIED"
        }

        logger.info(json.dumps(result))
        processed.append(result)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "SUCCESS",
            "processed_count": len(processed),
            "items": processed
        })
    }
