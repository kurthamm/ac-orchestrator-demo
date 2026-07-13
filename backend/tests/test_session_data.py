import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Mock boto3 before importing handler
sys.modules['boto3'] = MagicMock()

sys.path.insert(0, str(Path(__file__).parent.parent / "session-data"))
from handler import parse_session_arn

def test_parse_session_arn():
    arn = "arn:aws:wisdom:us-east-1:441700732419:session/64d2c0aa-0a40-4c36-bef5-93cdb40b61da/11111111-2222-3333-4444-555555555555"
    assert parse_session_arn(arn) == ("64d2c0aa-0a40-4c36-bef5-93cdb40b61da", "11111111-2222-3333-4444-555555555555")

def test_parse_session_arn_rejects_garbage():
    import pytest
    with pytest.raises(ValueError):
        parse_session_arn("not-an-arn")
