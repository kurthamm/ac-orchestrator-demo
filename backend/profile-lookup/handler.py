"""Lambda handler: resolve caller ANI (phone number) to memberId via AWS Customer Profiles.

Invoked from Connect inbound flow with phoneNumber parameter.
Returns flat STRING_MAP for Contact attributes: memberId, firstName, lastName, planName, lob, zip, language.
Fails fast: raises ValueError if phoneNumber missing, LookupError if no profile found or memberId missing.
"""
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

cp_client = boto3.client("customer-profiles")
DOMAIN_NAME = "amazon-connect-aetheriacc"


def _redact(v):
    """Redact sensitive values for logging: show last 4 chars only."""
    return f"...{str(v)[-4:]}" if v else "<empty>"


def lambda_handler(event, context):
    """
    Args:
        event: Lambda event from Connect flow with structure:
            {
                "Details": {
                    "Parameters": {
                        "phoneNumber": "<caller ANI>"
                    }
                }
            }
        context: Lambda context (unused)

    Returns:
        Flat string map:
        {
            "memberId": "...",
            "firstName": "...",
            "lastName": "...",
            "planName": "...",
            "lob": "...",
            "zip": "...",
            "language": "..."
        }

    Raises:
        ValueError: if phoneNumber is missing or empty
        LookupError: if no profile found or memberId missing from profile
    """
    # Extract phone number from Connect Lambda event
    phone_number = event.get("Details", {}).get("Parameters", {}).get("phoneNumber")
    if not phone_number:
        raise ValueError("phoneNumber is required and must not be empty")

    # Search Customer Profiles
    logger.info("Searching profiles for phone: %s", _redact(phone_number))
    response = cp_client.search_profiles(
        DomainName=DOMAIN_NAME,
        KeyName="_phone",
        Values=[phone_number]
    )

    # Validate exactly one match (or log warning if multiple, use first)
    items = response.get("Items", [])
    if not items:
        raise LookupError(f"No profile found for phone ending {_redact(phone_number)}")

    if len(items) > 1:
        logger.warning("Multiple profiles found for phone %s; using first", _redact(phone_number))

    profile = items[0]
    attributes = profile.get("Attributes", {})

    # Validate memberId exists
    member_id = attributes.get("memberId")
    if not member_id:
        raise LookupError(f"Profile for phone ending {_redact(phone_number)} missing memberId")

    # Extract fields (all as strings for Connect STRING_MAP)
    result = {
        "memberId": member_id,
        "firstName": attributes.get("firstName", ""),
        "lastName": attributes.get("lastName", ""),
        "planName": attributes.get("planName", ""),
        "lob": attributes.get("lob", ""),
        "zip": attributes.get("zip", ""),
        "language": attributes.get("language", "")
    }

    logger.info("Profile lookup successful: memberId=%s", _redact(member_id))
    return result
