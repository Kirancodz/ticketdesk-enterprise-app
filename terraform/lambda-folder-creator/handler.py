import json
import os
import re
import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")
BUCKET = os.environ["TICKETDESK_BUCKET"]


def create_if_missing(key, content, content_type):
    try:
        s3.put_object(
            Bucket=BUCKET,
            Key=key,
            Body=content,
            ContentType=content_type,
            IfNoneMatch="*"
        )
        return "CREATED"

    except ClientError as error:
        status = error.response.get(
            "ResponseMetadata", {}
        ).get("HTTPStatusCode")

        if status == 412:
            return "ALREADY_EXISTS"

        raise


def lambda_handler(event, context):
    ticket_id = event.get("ticket_id", "")

    if not re.fullmatch(r"TKT-[0-9]{4}-[0-9]{4,}", ticket_id):
        raise ValueError("Invalid ticket ID")

    prefix = f"TicketLogs/Tickets/{ticket_id}/"

    discussion = {
        "ticket_id": ticket_id,
        "comments": [],
        "last_synced_at": None
    }

    results = {}

    results["discussion"] = create_if_missing(
        prefix + "Discussiondetails.json",
        json.dumps(discussion).encode("utf-8"),
        "application/json"
    )

    results["attachments"] = create_if_missing(
        prefix + "Attachments/",
        b"",
        "application/octet-stream"
    )

    results["logs"] = create_if_missing(
        prefix + "Logdetails/",
        b"",
        "application/octet-stream"
    )

    return {
        "statusCode": 200,
        "ticket_id": ticket_id,
        "results": results
    }
