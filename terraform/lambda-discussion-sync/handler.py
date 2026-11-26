import json
import os
import re
import time
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")
BUCKET = os.environ["TICKETDESK_BUCKET"]


def lambda_handler(event, context):
    ticket_id = event.get("ticket_id", "")
    comment = event.get("comment")

    if not isinstance(ticket_id, str) or not re.fullmatch(
        r"TKT-[0-9]{4}-[0-9]{4,}", ticket_id
    ):
        raise ValueError("Invalid ticket ID")

    if not isinstance(comment, dict):
        raise ValueError("Missing comment")

    comment_id = comment.get("id")

    if type(comment_id) is not int or comment_id <= 0:
        raise ValueError("Invalid comment ID")

    if not isinstance(comment.get("body"), str):
        raise ValueError("Invalid comment body")

    record = {
        "id": comment_id,
        "author_id": comment.get("author_id"),
        "author_name": comment.get("author_name"),
        "body": comment["body"],
        "is_internal": comment.get("is_internal") is True,
        "created_at": comment.get("created_at"),
    }

    key = f"TicketLogs/Tickets/{ticket_id}/Discussiondetails.json"

    for attempt in range(6):
        etag = None

        try:
            response = s3.get_object(Bucket=BUCKET, Key=key)
            data = json.loads(response["Body"].read())
            etag = response["ETag"]

        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")

            if code not in ("NoSuchKey", "404", "NotFound"):
                raise

            data = {
                "ticket_id": ticket_id,
                "comments": [],
                "last_synced_at": None
            }

        if not isinstance(data, dict):
            raise ValueError("Invalid discussion document")

        if data.get("ticket_id") != ticket_id:
            raise ValueError("Ticket ID mismatch in discussion document")

        comments = data.get("comments")

        if not isinstance(comments, list):
            raise ValueError("Invalid comments list")

        if any(existing.get("id") == comment_id for existing in comments):
            return {
                "statusCode": 200,
                "ticket_id": ticket_id,
                "result": "ALREADY_SYNCED"
            }

        comments.append(record)
        comments.sort(key=lambda item: item["id"])

        data["last_synced_at"] = datetime.now(timezone.utc).isoformat()

        arguments = {
            "Bucket": BUCKET,
            "Key": key,
            "Body": json.dumps(data, ensure_ascii=False).encode("utf-8"),
            "ContentType": "application/json"
        }

        if etag:
            arguments["IfMatch"] = etag
        else:
            arguments["IfNoneMatch"] = "*"

        try:
            s3.put_object(**arguments)

            return {
                "statusCode": 200,
                "ticket_id": ticket_id,
                "result": "SYNCED",
                "comment_id": comment_id
            }

        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")

            if code not in ("PreconditionFailed", "ConditionalRequestConflict"):
                raise

            time.sleep(0.1 * (attempt + 1))

    raise RuntimeError("Discussion sync conflict; retry required")
