"""Centene Demo IVR — fulfillment Lambda.

Single Lambda exposing 8 member-services tools to the Amazon Connect AI Agent
via AgentCore Gateway (MCP). Backed entirely by JSON fixtures bundled in the
deployment package — no external systems are called.

Invocation contract (AgentCore Gateway → Lambda):
    event = {
        "tool_name": "verify_eligibility",
        "arguments": { ... },
        "session_attributes": { "member_id": "99999100001", ... }
    }

Return:
    { "ok": True, "data": { ... } }   on success
    { "ok": False, "error": "..." }   on failure (the agent reads + reacts)
"""
import json
import logging
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger()
logger.setLevel(logging.INFO)

FIXTURE_DIR = Path(os.environ.get("FIXTURE_DIR", Path(__file__).parent / "fixtures"))


@lru_cache(maxsize=16)
def _load(name: str):
    with open(FIXTURE_DIR / f"{name}.json") as f:
        return json.load(f)


def _members():
    return _load("members")["members"]


def _claims():
    return _load("claims")["claims"]


def _benefits():
    return _load("benefits")


def _accumulators():
    return _load("accumulators")["accumulators"]


def _providers():
    return _load("providers")["providers"]


def _flex_cards():
    return _load("flex_cards")["flex_cards"]


def _eobs():
    return _load("eobs")["eobs"]


def _find_member(member_id):
    return next((m for m in _members() if m["member_id"] == member_id), None)


def _find_accumulator(member_id):
    return next((a for a in _accumulators() if a["member_id"] == member_id), None)


def ok(data):
    return {"ok": True, "data": data}


def err(message, code="not_found"):
    return {"ok": False, "error": message, "error_code": code}


# ---------------------------------------------------------------------------
# Tool 1: verify_eligibility
# ---------------------------------------------------------------------------
def verify_eligibility(args, session):
    member_id = session["member_id"]
    m = _find_member(member_id)
    if not m:
        return err("Member not found")
    return ok({
        "status": m["status"],
        "plan_name": m["plan_name"],
        "lob": m["lob"],
        "effective_date": m["effective_date"],
        "term_date": m.get("term_date"),
        "grace_period_end": m.get("grace_period_end"),
        "additional_plans": m.get("additional_plans", []),
    })


# ---------------------------------------------------------------------------
# Tool 2: request_id_card
# ---------------------------------------------------------------------------
def request_id_card(args, session):
    member_id = session["member_id"]
    m = _find_member(member_id)
    if not m:
        return err("Member not found")

    delivery_method = args.get("delivery_method", "mail").lower()
    for_whom = args.get("for_whom", "self").lower()
    dependent_id = args.get("dependent_id")

    if delivery_method == "digital" and not m.get("email"):
        return err("No email on file. Mail delivery only.", code="no_email")
    if for_whom == "dependent" and not m.get("dependents"):
        return err("No dependents on file for this member.", code="no_dependents")

    target_addr = m["address"]
    target_email = m.get("email") if delivery_method in ("digital", "both") else None
    return ok({
        "delivery_method": delivery_method,
        "for_whom": for_whom,
        "dependent_id": dependent_id,
        "address_on_file": target_addr,
        "email_on_file": target_email,
        "digital_eta_minutes": 5 if delivery_method in ("digital", "both") else None,
        "mail_eta_business_days": "7-10" if delivery_method in ("mail", "both") else None,
        "request_id": f"IDC{int(datetime.now(timezone.utc).timestamp())}",
    })


# ---------------------------------------------------------------------------
# Tool 3: check_claim_status
# ---------------------------------------------------------------------------
def check_claim_status(args, session):
    member_id = session["member_id"]
    claim_id = args.get("claim_id")
    provider_name = args.get("provider_name")
    service_date = args.get("service_date")

    matches = [c for c in _claims() if c["member_id"] == member_id]
    if claim_id:
        matches = [c for c in matches if c["claim_id"] == claim_id]
    if provider_name:
        matches = [c for c in matches if provider_name.lower() in c["provider_name"].lower()]
    if service_date:
        matches = [c for c in matches if c["service_date"] == service_date]

    if not matches:
        return err("No matching claims found.", code="no_match")

    matches.sort(key=lambda c: c["service_date"], reverse=True)

    if len(matches) == 1:
        return ok({"match_count": 1, "claim": matches[0]})
    return ok({
        "match_count": len(matches),
        "claims_summary": [
            {
                "claim_id": c["claim_id"],
                "provider_name": c["provider_name"],
                "service_date": c["service_date"],
                "status": c["status"],
                "billed_amount": c["billed_amount"],
            }
            for c in matches[:5]
        ],
    })


# ---------------------------------------------------------------------------
# Tool 4: check_benefit_coverage
# ---------------------------------------------------------------------------
def check_benefit_coverage(args, session):
    member_id = session["member_id"]
    service_type = (args.get("service_type") or "").strip().lower()
    if not service_type:
        return err("service_type is required", code="missing_arg")

    m = _find_member(member_id)
    if not m:
        return err("Member not found")

    plans = _benefits()["plans"]
    synonyms = _benefits()["service_synonyms"]
    plan = plans.get(m["plan_name"])
    if not plan:
        return err(f"No benefit data for plan {m['plan_name']}")

    benefit_key = synonyms.get(service_type, service_type)
    benefit = plan["benefits"].get(benefit_key)
    if not benefit:
        return err(f"Service '{service_type}' is not on the standard benefit grid for your plan.", code="not_on_grid")

    accumulator = _find_accumulator(member_id)
    return ok({
        "service_type": benefit_key,
        "plan_name": m["plan_name"],
        "benefit": benefit,
        "deductible_status": {
            "met": accumulator["deductible_met"] if accumulator else 0,
            "total": accumulator["deductible_total"] if accumulator else 0,
        } if benefit.get("deductible_applies") else None,
        "moop_status": {
            "met": accumulator["moop_met"] if accumulator else 0,
            "total": accumulator["moop_total"] if accumulator else 0,
        } if accumulator else None,
    })


# ---------------------------------------------------------------------------
# Tool 5: change_pcp
# ---------------------------------------------------------------------------
def change_pcp(args, session):
    member_id = session["member_id"]
    new_pcp_npi = args.get("new_pcp_npi")
    new_pcp_name_query = args.get("new_pcp_name")
    effective_date_pref = args.get("effective_date_preference", "immediate")
    confirmed = args.get("confirmed", False)

    m = _find_member(member_id)
    if not m:
        return err("Member not found")

    if new_pcp_npi:
        provider = next((p for p in _providers() if p["npi"] == new_pcp_npi), None)
        candidates = [provider] if provider else []
    elif new_pcp_name_query:
        q = new_pcp_name_query.lower()
        candidates = [
            p for p in _providers()
            if p["is_pcp_eligible"] and (
                q in p["last_name"].lower() or q in p["first_name"].lower()
                or q in f"{p['first_name']} {p['last_name']}".lower()
            )
        ]
    else:
        return err("Provide new_pcp_npi or new_pcp_name", code="missing_arg")

    if not candidates:
        return err("No PCP-eligible provider found.", code="no_match")

    if len(candidates) > 1:
        return ok({
            "needs_disambiguation": True,
            "candidates": [
                {
                    "npi": p["npi"],
                    "name": f"Dr. {p['first_name']} {p['last_name']}",
                    "specialty": p["specialty"],
                    "practice_name": p["practice_name"],
                    "address": p["address"],
                    "accepting_new_patients": p["accepting_new_patients"],
                }
                for p in candidates
            ],
        })

    p = candidates[0]
    if not p["in_network"]:
        return err(f"Dr. {p['last_name']} is not in network.", code="out_of_network")
    if not p["accepting_new_patients"]:
        return err(f"Dr. {p['last_name']} is not currently accepting new patients.", code="not_accepting")

    if not confirmed:
        return ok({
            "needs_confirmation": True,
            "preview": {
                "previous_pcp_npi": m["current_pcp_npi"],
                "new_pcp_npi": p["npi"],
                "new_pcp_name": f"Dr. {p['first_name']} {p['last_name']}",
                "practice_name": p["practice_name"],
                "effective_date_preference": effective_date_pref,
            },
        })

    # Demo-only: confirmed write goes to /tmp, not persisted.
    today = datetime.now(timezone.utc).date().isoformat()
    record = {
        "member_id": member_id,
        "previous_pcp_npi": m["current_pcp_npi"],
        "new_pcp_npi": p["npi"],
        "effective_date": today if effective_date_pref == "immediate" else effective_date_pref,
        "change_timestamp": datetime.now(timezone.utc).isoformat(),
        "channel": "ivr",
    }
    try:
        with open("/tmp/pcp_change.json", "w") as f:
            json.dump(record, f)
    except OSError:
        pass
    return ok({
        "committed": True,
        "record": record,
        "id_card_eta_business_days": "7-10",
    })


# ---------------------------------------------------------------------------
# Tool 6: explain_eob
# ---------------------------------------------------------------------------
def explain_eob(args, session):
    member_id = session["member_id"]
    eob_id = args.get("eob_id")
    claim_id = args.get("claim_id")

    eobs = [e for e in _eobs() if e["member_id"] == member_id]
    if eob_id:
        eobs = [e for e in eobs if e["eob_id"] == eob_id]
    elif claim_id:
        eobs = [e for e in eobs if claim_id in e["claim_ids"]]

    if not eobs:
        return err("No matching EOB found for this member.", code="no_match")

    e = eobs[0]
    related = [c for c in _claims() if c["claim_id"] in e["claim_ids"]]
    return ok({
        "eob": e,
        "related_claims": related,
    })


# ---------------------------------------------------------------------------
# Tool 7: check_flex_card_balance
# ---------------------------------------------------------------------------
def check_flex_card_balance(args, session):
    member_id = session["member_id"]
    cards = [c for c in _flex_cards() if c["member_id"] == member_id]
    if not cards:
        return err("No flex card on file for this member.", code="no_card")
    return ok({"cards": cards})


# ---------------------------------------------------------------------------
# Tool 8: search_provider_directory
# ---------------------------------------------------------------------------
def search_provider_directory(args, session):
    specialty = (args.get("specialty") or "").lower().strip()
    name_query = (args.get("name_query") or "").lower().strip()
    location_zip = args.get("location_zip") or _find_member(session["member_id"])["address"]["zip"]
    accepting_new = args.get("accepting_new_only", False)
    in_network_only = args.get("in_network_only", True)

    results = list(_providers())
    if specialty:
        results = [p for p in results if specialty in p["specialty"].lower()]
    if name_query:
        results = [
            p for p in results
            if name_query in p["last_name"].lower() or name_query in p["first_name"].lower()
        ]
    if accepting_new:
        results = [p for p in results if p["accepting_new_patients"]]
    if in_network_only:
        results = [p for p in results if p["in_network"]]

    # Crude proximity sort: same zip first, then alphabetical.
    results.sort(key=lambda p: (p["distance_zip_seed"] != location_zip, p["last_name"]))

    if not results:
        return err("No providers match those filters.", code="no_match")

    return ok({
        "match_count": len(results),
        "providers": [
            {
                "npi": p["npi"],
                "name": f"Dr. {p['first_name']} {p['last_name']}",
                "specialty": p["specialty"],
                "practice_name": p["practice_name"],
                "address": p["address"],
                "phone": p["phone"],
                "in_network": p["in_network"],
                "accepting_new_patients": p["accepting_new_patients"],
                "languages": p.get("languages", []),
                "same_zip_as_member": p["distance_zip_seed"] == location_zip,
            }
            for p in results[:10]
        ],
    })


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
TOOLS = {
    "verify_eligibility": verify_eligibility,
    "request_id_card": request_id_card,
    "check_claim_status": check_claim_status,
    "check_benefit_coverage": check_benefit_coverage,
    "change_pcp": change_pcp,
    "explain_eob": explain_eob,
    "check_flex_card_balance": check_flex_card_balance,
    "search_provider_directory": search_provider_directory,
}


def lambda_handler(event, context):
    logger.info("event: %s", json.dumps(event))
    tool_name = event.get("tool_name")
    arguments = event.get("arguments") or {}
    session = event.get("session_attributes") or {}

    if not tool_name:
        return err("tool_name is required", code="missing_tool")
    if "member_id" not in session:
        return err("session_attributes.member_id is required (auth must run first)", code="not_authenticated")

    handler = TOOLS.get(tool_name)
    if not handler:
        return err(f"Unknown tool: {tool_name}", code="unknown_tool")

    try:
        result = handler(arguments, session)
    except Exception as exc:
        logger.exception("tool %s raised", tool_name)
        return err(f"Tool {tool_name} failed: {exc}", code="tool_exception")

    logger.info("result: %s", json.dumps(result))
    return result
