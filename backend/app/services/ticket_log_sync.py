import json
import logging

import boto3
from botocore.config import Config
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine
from app.models.ticket import Ticket, TicketHistory
from app.models.user import User

logger = logging.getLogger("ticketdesk.log_sync")

PENDING_KEY = "ticketdesk_pending_history_ids"


@event.listens_for(Session, "after_flush")
def collect_ticket_history(session, flush_context):
    if settings.STORAGE_PROVIDER.lower() != "s3":
        return

    history_ids = {
        item.id
        for item in session.new
        if isinstance(item, TicketHistory) and item.id is not None
    }

    if history_ids:
        session.info.setdefault(PENDING_KEY, set()).update(history_ids)


@event.listens_for(Session, "after_soft_rollback")
def clear_rolled_back_history(session, previous_transaction):
    if not session.in_transaction():
        session.info.pop(PENDING_KEY, None)


@event.listens_for(Session, "after_commit")
def synchronize_committed_history(session):
    if session.in_nested_transaction():
        return

    history_ids = session.info.pop(PENDING_KEY, set())

    if not history_ids or settings.STORAGE_PROVIDER.lower() != "s3":
        return

    try:
        query = (
            select(
                TicketHistory.id,
                Ticket.ticket_number,
                TicketHistory.actor_id,
                User.full_name.label("actor_name"),
                TicketHistory.action,
                TicketHistory.field_name,
                TicketHistory.old_value,
                TicketHistory.new_value,
                TicketHistory.description,
                TicketHistory.created_at,
            )
            .join(Ticket, Ticket.id == TicketHistory.ticket_id)
            .outerjoin(User, User.id == TicketHistory.actor_id)
            .where(TicketHistory.id.in_(history_ids))
            .order_by(TicketHistory.id)
        )

        with engine.connect() as connection:
            records = connection.execute(query).mappings().all()

        client = boto3.client(
            "lambda",
            region_name=settings.AWS_REGION,
            config=Config(
                connect_timeout=2,
                read_timeout=3,
                retries={"mode": "standard", "max_attempts": 3},
            ),
        )

        for record in records:
            payload = {
                "ticket_id": record["ticket_number"],
                "history": {
                    "event_id": record["id"],
                    "actor_id": record["actor_id"],
                    "actor_name": record["actor_name"],
                    "action": record["action"],
                    "field_name": record["field_name"],
                    "old_value": record["old_value"],
                    "new_value": record["new_value"],
                    "description": record["description"],
                    "created_at": record["created_at"].isoformat(),
                },
            }

            try:
                response = client.invoke(
                    FunctionName="ticketdesk-log-processor",
                    InvocationType="Event",
                    Payload=json.dumps(payload).encode("utf-8"),
                )

                if response.get("StatusCode") != 202:
                    logger.error(
                        "Unexpected Log Processor response for event %s",
                        record["id"],
                    )

            except Exception:
                logger.exception(
                    "Failed to queue history event %s",
                    record["id"],
                )

    except Exception:
        logger.exception("Ticket history synchronization failed")
