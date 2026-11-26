import json
import logging

import boto3
from botocore.config import Config

from app.core.config import settings

logger = logging.getLogger("ticketdesk.discussion_sync")


def queue_ticket_discussion_sync(ticket_number, comment, author_name):
    if settings.STORAGE_PROVIDER.lower() != "s3":
        return

    payload = {
        "ticket_id": ticket_number,
        "comment": {
            "id": comment.id,
            "author_id": comment.author_id,
            "author_name": author_name,
            "body": comment.body,
            "is_internal": comment.is_internal,
            "created_at": comment.created_at.isoformat(),
        },
    }

    try:
        client = boto3.client(
            "lambda",
            region_name=settings.AWS_REGION,
            config=Config(
                connect_timeout=2,
                read_timeout=3,
                retries={"max_attempts": 1},
            ),
        )

        response = client.invoke(
            FunctionName="ticketdesk-discussion-sync",
            InvocationType="Event",
            Payload=json.dumps(payload).encode("utf-8"),
        )

        if response.get("StatusCode") != 202:
            logger.error(
                "Unexpected Discussion Sync response for ticket %s: %s",
                ticket_number,
                response.get("StatusCode"),
            )

    except Exception:
        logger.exception(
            "Failed to queue Discussion Sync for ticket %s",
            ticket_number,
        )
