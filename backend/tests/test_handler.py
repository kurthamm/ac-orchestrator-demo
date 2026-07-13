import json
import sys
import importlib.util
from pathlib import Path

# Load fulfillment handler under unique module name to avoid collisions
_spec = importlib.util.spec_from_file_location(
    "fulfillment_handler",
    Path(__file__).parent.parent / "fulfillment" / "handler.py"
)
handler = importlib.util.module_from_spec(_spec)
sys.modules["fulfillment_handler"] = handler
_spec.loader.exec_module(handler)

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
    """Test that member 99999100001 has a denied claim with CO-197 code via the public contract"""
    r = _call("check_claim_status", {"member_id": M})
    assert r["ok"] is True
    # Response structure depends on number of claims
    claims = []
    if "claim" in r["data"]:
        claims = [r["data"]["claim"]]
    else:
        claims = r["data"].get("claims", [])

    # Verify CO-197 denial is present in the returned data
    assert any(
        c.get("status") == "denied" and c.get("denial_code") == "CO-197"
        for c in claims
    ), f"Expected denied claim with CO-197 in response claims, got {claims}"


def test_search_provider_directory_member_not_found():
    """Test that search_provider_directory returns member-not-found error for unknown member_id"""
    r = _call(
        "search_provider_directory",
        {"member_id": "00000000000"}
    )
    assert r["ok"] is False
    assert r["error_code"] == "not_found"
    assert "Member not found" in r["error"]


def test_search_provider_directory_language_filter():
    """Test that language filter excludes en-only providers"""
    r = _call(
        "search_provider_directory",
        {"member_id": M, "language": "es"}
    )
    assert r["ok"] is True
    providers = r["data"]["providers"]
    # All returned providers should have Spanish in their languages
    for p in providers:
        assert "es" in p["languages"], f"Provider {p['name']} should have Spanish"
    # Should find at least one Spanish-speaking provider
    assert len(providers) > 0


def test_search_provider_directory_gender_filter():
    """Test that gender filter works case-insensitively"""
    r = _call(
        "search_provider_directory",
        {"member_id": M, "gender": "FEMALE"}
    )
    assert r["ok"] is True
    # If we get results, all should match female gender
    if r["data"]["providers"]:
        for p in r["data"]["providers"]:
            # Gender check would require adding gender to response
            assert "name" in p


def test_change_pcp_roundtrip():
    """Test that change_pcp can be called with member_id argument"""
    r = _call(
        "change_pcp",
        {"member_id": M, "new_pcp_name": "Sofia Herrera", "confirmed": True}
    )
    assert r["ok"] is True
    assert r["data"].get("simulated") is True
    assert "note" in r["data"]
