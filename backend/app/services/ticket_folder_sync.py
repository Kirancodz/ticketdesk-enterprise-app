import json
import logging

import boto3
from botocore.config import Config

from app.core.config import settings

logger = logging.getLogger("ticketdesk.folder_sync")


def queue_ticket_folder_creation(ticket_number: str) -> None:
    if settings.STORAGE_PROVIDER.lower() != "s3":
        return

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
            FunctionName="ticketdesk-folder-creator",
            InvocationType="Event",
            Payload=json.dumps(
                {"ticket_id": ticket_number}
            ).encode("utf-8"),
        )

        if response.get("StatusCode") != 202:
            logger.error(
                "Unexpected Folder Creator response for ticket %s: %s",
                ticket_number,
                response.get("StatusCode"),
            )

    except Exception:
        logger.exception(
            "Failed to queue S3 folder creation for ticket %s",
            ticket_number,
        )
