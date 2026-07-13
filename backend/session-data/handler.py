"""Flow Lambda: push memberId contact attribute into the contact's Q in Connect session.

Placed AFTER the Connect assistant block in the inbound flow. Fails loudly:
a missing memberId or session means the flow is miswired — surface it, don't mask it.
"""
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)
connect = boto3.client("connect")
qconnect = boto3.client("qconnect")

INSTANCE_ID = "d232199a-e1f4-4d84-a77e-10f8bfc6468f"


def parse_session_arn(arn: str):
    parts = arn.split(":session/")
    if len(parts) != 2 or "/" not in parts[1]:
        raise ValueError(f"unexpected Wisdom session ARN: {arn}")
    assistant_id, session_id = parts[1].split("/", 1)
    return assistant_id, session_id


def lambda_handler(event, context):
    details = event["Details"]
    contact_id = details["ContactData"]["ContactId"]
    member_id = details["Parameters"].get("memberId") or details["ContactData"]["Attributes"].get("memberId")
    if not member_id:
        raise ValueError("memberId missing: profile lookup did not run or found no match")

    contact = connect.describe_contact(InstanceId=INSTANCE_ID, ContactId=contact_id)["Contact"]
    session_arn = contact["WisdomInfo"]["SessionArn"]
    assistant_id, session_id = parse_session_arn(session_arn)

    qconnect.update_session_data(
        assistantId=assistant_id, sessionId=session_id,
        data=[{"key": "memberId", "value": {"stringValue": member_id}}],
    )
    logger.info("memberId=%s pushed to session %s", member_id, session_id)
    return {"status": "ok", "memberId": member_id}
