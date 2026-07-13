import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

# Mock boto3 before importing handler
sys.modules['boto3'] = MagicMock()

sys.path.insert(0, str(Path(__file__).parent.parent / "session-data"))
from handler import parse_session_arn, lambda_handler

def test_parse_session_arn():
    arn = "arn:aws:wisdom:us-east-1:441700732419:session/64d2c0aa-0a40-4c36-bef5-93cdb40b61da/11111111-2222-3333-4444-555555555555"
    assert parse_session_arn(arn) == ("64d2c0aa-0a40-4c36-bef5-93cdb40b61da", "11111111-2222-3333-4444-555555555555")

def test_parse_session_arn_rejects_garbage():
    with pytest.raises(ValueError):
        parse_session_arn("not-an-arn")

def test_lambda_handler_calls_update_session_with_orchestrator_agent():
    """Verify update_session is called with orchestrator config and AI agent ID from env var."""
    with patch.dict(os.environ, {"ORCHESTRATOR_AI_AGENT_ID": "62f706c6-f5e8-4580-ab7d-5d5669751376:4"}):
        # Mock the boto3 clients
        mock_connect = MagicMock()
        mock_qconnect = MagicMock()

        with patch("handler.connect", mock_connect), \
             patch("handler.qconnect", mock_qconnect):

            # Set up mock responses
            mock_connect.describe_contact.return_value = {
                "Contact": {
                    "WisdomInfo": {
                        "SessionArn": "arn:aws:wisdom:us-east-1:441700732419:session/64d2c0aa-0a40-4c36-bef5-93cdb40b61da/11111111-2222-3333-4444-555555555555"
                    }
                }
            }

            event = {
                "Details": {
                    "ContactData": {
                        "ContactId": "contact-123",
                        "Attributes": {"memberId": "99999100001"}
                    },
                    "Parameters": {}
                }
            }

            result = lambda_handler(event, None)

            # Verify update_session was called with orchestrator config
            mock_qconnect.update_session.assert_called_once_with(
                assistantId="64d2c0aa-0a40-4c36-bef5-93cdb40b61da",
                sessionId="11111111-2222-3333-4444-555555555555",
                orchestratorConfigurationList=[
                    {
                        "aiAgentId": "62f706c6-f5e8-4580-ab7d-5d5669751376:4",
                        "orchestratorUseCase": "Connect.AgentAssistance"
                    }
                ]
            )

            # Verify update_session_data was also called
            mock_qconnect.update_session_data.assert_called_once()

            assert result["status"] == "ok"
            assert result["memberId"] == "99999100001"

def test_lambda_handler_raises_on_missing_orchestrator_env_var():
    """Verify handler raises KeyError when ORCHESTRATOR_AI_AGENT_ID env var is missing."""
    with patch.dict(os.environ, {}, clear=True):
        mock_connect = MagicMock()
        mock_qconnect = MagicMock()

        with patch("handler.connect", mock_connect), \
             patch("handler.qconnect", mock_qconnect):

            mock_connect.describe_contact.return_value = {
                "Contact": {
                    "WisdomInfo": {
                        "SessionArn": "arn:aws:wisdom:us-east-1:441700732419:session/64d2c0aa-0a40-4c36-bef5-93cdb40b61da/11111111-2222-3333-4444-555555555555"
                    }
                }
            }

            event = {
                "Details": {
                    "ContactData": {
                        "ContactId": "contact-123",
                        "Attributes": {"memberId": "99999100001"}
                    },
                    "Parameters": {}
                }
            }

            with pytest.raises(KeyError):
                lambda_handler(event, None)
