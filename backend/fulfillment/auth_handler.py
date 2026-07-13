"""Centene Demo IVR — DTMF auth Lambda.

Invoked from the Connect contact flow before the AI Agent block. Validates the
caller's 11-digit member ID against the members fixture and returns contact
attributes that flow into the AI Agent as session attributes.
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger()
logger.setLevel(logging.INFO)

FIXTURE_DIR = Path(os.environ.get("FIXTURE_DIR", Path(__file__).parent / "fixtures"))

with open(FIXTURE_DIR / "members.json") as _f:
    _MEMBERS = json.load(_f)["members"]


def lambda_handler(event, context):
    logger.info("event: %s", json.dumps(event))
    member_id = event.get("Details", {}).get("Parameters", {}).get("MemberId", "").strip()

    if not member_id:
        return {"auth_status": "failed", "reason": "no_member_id_provided"}

    member = next((m for m in _MEMBERS if m["member_id"] == member_id), None)
    if not member:
        return {"auth_status": "failed", "reason": "member_not_found"}

    return {
        "auth_status": "success",
        "member_id": member["member_id"],
        "first_name": member["first_name"],
        "last_name": member["last_name"],
        "plan_name": member["plan_name"],
        "lob": member["lob"],
    }
