import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "fulfillment"))
import handler

M = "99999100001"


def _call(tool, arguments):
    return handler.lambda_handler(
        {
            "tool_name": tool,
            "arguments": arguments,
            "session_attributes": {}
        },
        None
    )


def test_member_id_accepted_as_argument():
    """Test that member_id can be passed as tool argument"""
    r = _call("verify_eligibility", {"member_id": M})
    assert r["ok"] is True
    assert r["data"]["status"] == "active"


def test_missing_member_id_fails_fast():
    """Test that missing member_id returns not_authenticated error"""
    r = _call("verify_eligibility", {})
    assert r["ok"] is False
    assert r["error_code"] == "not_authenticated"


def test_current_pcp_is_alvarez():
    """Test that member 99999100001 has Dr. Elena Alvarez as current PCP"""
    r = _call("verify_eligibility", {"member_id": M})
    assert "Alvarez" in json.dumps(r["data"])


def test_spanish_pcp_search_finds_candidates():
    """Test that search_provider_directory finds Spanish-speaking PCPs in zip 29201"""
    r = _call(
        "search_provider_directory",
        {
            "member_id": M,
            "specialty": "Family Medicine",
            "in_network_only": True,
            "accepting_new_only": True
        }
    )
    assert r["ok"] is True
    hits = r["data"]["providers"]
    # Filter for Spanish-speaking providers in zip 29201
    spanish_speakers = [
        p for p in hits
        if p["same_zip_as_member"] and "es" in p["languages"]
    ]
    assert len(spanish_speakers) >= 2


def test_denied_claim_exists():
    """Test that member 99999100001 has a denied claim with CO-197 code"""
    r = _call("check_claim_status", {"member_id": M})
    assert r["ok"] is True
    # Response structure depends on number of claims
    if "claim" in r["data"]:
        claims = [r["data"]["claim"]]
    else:
        claims = r["data"].get("claims_summary", [])
    # For multiple claims, check full claim objects
    all_claims = handler._claims()
    member_claims = [c for c in all_claims if c["member_id"] == M]
    assert any(
        c.get("status") == "denied" and c.get("denial_code") == "CO-197"
        for c in member_claims
    )


def test_change_pcp_roundtrip():
    """Test that change_pcp can be called with member_id argument"""
    r = _call(
        "change_pcp",
        {"member_id": M, "new_pcp_name": "Sofia Herrera", "confirmed": True}
    )
    assert r["ok"] is True
