import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ssm = boto3.client("ssm")

INSTANCE_ID = os.environ["TICKETDESK_EC2_INSTANCE_ID"]
DOCUMENT_NAME = os.environ["TICKETDESK_SLA_SSM_DOCUMENT"]


def lambda_handler(event, context):
    response = ssm.send_command(
        InstanceIds=[INSTANCE_ID],
        DocumentName=DOCUMENT_NAME,
        Comment="TicketDesk scheduled SLA monitoring",
        TimeoutSeconds=120,
    )

    command_id = response["Command"]["CommandId"]

    logger.info("SLA monitoring command submitted: %s", command_id)

    return {
        "statusCode": 202,
        "status": "SUBMITTED",
        "command_id": command_id,
        "instance_id": INSTANCE_ID,
    }
