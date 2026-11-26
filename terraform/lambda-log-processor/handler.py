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
    ticket_id = event.get("ticket_id")
    history = event.get("history")

    if not isinstance(ticket_id, str) or not re.fullmatch(
        r"TKT-[0-9]{4}-[0-9]{4,}", ticket_id
    ):
        raise ValueError("Invalid ticket ID")

    if not isinstance(history, dict):
        raise ValueError("Missing history event")

    event_id = history.get("event_id")

    if type(event_id) is not int or event_id <= 0:
        raise ValueError("Invalid history event ID")

    for field in ("action", "description", "created_at"):
        if not isinstance(history.get(field), str) or not history[field]:
            raise ValueError(f"Invalid history field: {field}")

    record = {
        "event_id": event_id,
        "actor_id": history.get("actor_id"),
        "actor_name": history.get("actor_name"),
        "action": history["action"],
        "field_name": history.get("field_name"),
        "old_value": history.get("old_value"),
        "new_value": history.get("new_value"),
        "description": history["description"],
        "created_at": history["created_at"]
    }

    key = f"TicketLogs/Tickets/{ticket_id}/Logdetails/Logdetails.json"

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
                "total_events": 0,
                "last_updated": None,
                "events": []
            }

        if not isinstance(data, dict) or data.get("ticket_id") != ticket_id:
            raise ValueError("Invalid ticket log document")

        events = data.get("events")

        if not isinstance(events, list):
            raise ValueError("Invalid events list")

        if any(
            isinstance(item, dict) and item.get("event_id") == event_id
            for item in events
        ):
            return {
                "statusCode": 200,
                "ticket_id": ticket_id,
                "result": "ALREADY_SYNCED"
            }

        events.append(record)
        events.sort(
            key=lambda item: (
                item.get("created_at") or "",
                item["event_id"]
            )
        )

        data["total_events"] = len(events)
        data["last_updated"] = datetime.now(timezone.utc).isoformat()

        arguments = {
            "Bucket": BUCKET,
            "Key": key,
            "Body": json.dumps(data, ensure_ascii=False).encode("utf-8"),
            "ContentType": "application/json",
            "ServerSideEncryption": "AES256"
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
                "event_id": event_id,
                "total_events": len(events)
            }

        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")

            if code not in (
                "PreconditionFailed",
                "ConditionalRequestConflict"
            ):
                raise

            time.sleep(0.1 * (attempt + 1))

    raise RuntimeError("Log synchronization conflict; retry required")
