import sys
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Mock boto3 before importing handler
sys.modules['boto3'] = MagicMock()

# Load profile-lookup handler under unique module name to avoid collisions
_spec = importlib.util.spec_from_file_location(
    "profile_lookup_handler",
    Path(__file__).parent.parent / "profile-lookup" / "handler.py"
)
_handler_module = importlib.util.module_from_spec(_spec)
sys.modules["profile_lookup_handler"] = _handler_module
_spec.loader.exec_module(_handler_module)

lambda_handler = _handler_module.lambda_handler


def test_profile_lookup_happy_path():
    """Test successful profile lookup returns flat string map."""
    mock_profiles_client = MagicMock()
    mock_profiles_client.search_profiles.return_value = {
        'Items': [
            {
                'ProfileId': 'profile-123',
                'Attributes': {
                    'memberId': '99999100001',
                    'firstName': 'John',
                    'lastName': 'Doe',
                    'planName': 'Medicare Advantage',
                    'lob': 'Medicare',
                    'zip': '80301',
                    'language': 'en'
                }
            }
        ]
    }

    event = {
        'Details': {
            'Parameters': {
                'phoneNumber': '+18036060039'
            }
        }
    }

    with patch('profile_lookup_handler.cp_client', mock_profiles_client):
        result = lambda_handler(event, None)

    assert result == {
        'memberId': '99999100001',
        'firstName': 'John',
        'lastName': 'Doe',
        'planName': 'Medicare Advantage',
        'lob': 'Medicare',
        'zip': '80301',
        'language': 'en'
    }

    # Verify Customer Profiles was called correctly
    mock_profiles_client.search_profiles.assert_called_once_with(
        DomainName='amazon-connect-aetheriacc',
        KeyName='_phone',
        Values=['+18036060039']
    )


def test_profile_lookup_missing_phone_number():
    """Test that missing phoneNumber raises ValueError."""
    event = {
        'Details': {
            'Parameters': {}
        }
    }

    with pytest.raises(ValueError) as exc_info:
        lambda_handler(event, None)

    assert 'phonenumber' in str(exc_info.value).lower()


def test_profile_lookup_empty_phone_number():
    """Test that empty phoneNumber raises ValueError."""
    event = {
        'Details': {
            'Parameters': {
                'phoneNumber': ''
            }
        }
    }

    with pytest.raises(ValueError) as exc_info:
        lambda_handler(event, None)

    assert 'phonenumber' in str(exc_info.value).lower()


def test_profile_lookup_no_match():
    """Test that no profile found raises LookupError with redacted phone number."""
    mock_profiles_client = MagicMock()
    mock_profiles_client.search_profiles.return_value = {
        'Items': []
    }

    event = {
        'Details': {
            'Parameters': {
                'phoneNumber': '+15555550100'
            }
        }
    }

    with patch('profile_lookup_handler.cp_client', mock_profiles_client):
        with pytest.raises(LookupError) as exc_info:
            lambda_handler(event, None)

    # Error message should contain last 4 digits of phone (redacted)
    assert '0100' in str(exc_info.value)
    assert 'No profile found' in str(exc_info.value)


def test_profile_lookup_multiple_matches():
    """Test that multiple matches use first but log warning."""
    mock_profiles_client = MagicMock()
    mock_profiles_client.search_profiles.return_value = {
        'Items': [
            {
                'ProfileId': 'profile-123',
                'Attributes': {
                    'memberId': '99999100001',
                    'firstName': 'John',
                    'lastName': 'Doe',
                    'planName': 'Medicare Advantage',
                    'lob': 'Medicare',
                    'zip': '80301',
                    'language': 'en'
                }
            },
            {
                'ProfileId': 'profile-456',
                'Attributes': {
                    'memberId': '99999100002',
                    'firstName': 'Jane',
                    'lastName': 'Smith',
                    'planName': 'Commercial',
                    'lob': 'BCBS',
                    'zip': '80302',
                    'language': 'es'
                }
            }
        ]
    }

    event = {
        'Details': {
            'Parameters': {
                'phoneNumber': '+18036060039'
            }
        }
    }

    with patch('profile_lookup_handler.cp_client', mock_profiles_client):
        result = lambda_handler(event, None)

    # Should return first match
    assert result['memberId'] == '99999100001'
    assert result['firstName'] == 'John'


def test_profile_lookup_missing_member_id():
    """Test that missing memberId in profile raises LookupError."""
    mock_profiles_client = MagicMock()
    mock_profiles_client.search_profiles.return_value = {
        'Items': [
            {
                'ProfileId': 'profile-123',
                'Attributes': {
                    'firstName': 'John',
                    'lastName': 'Doe'
                    # memberId is missing!
                }
            }
        ]
    }

    event = {
        'Details': {
            'Parameters': {
                'phoneNumber': '+18036060039'
            }
        }
    }

    with patch('profile_lookup_handler.cp_client', mock_profiles_client):
        with pytest.raises(LookupError) as exc_info:
            lambda_handler(event, None)

    assert 'memberid' in str(exc_info.value).lower()
