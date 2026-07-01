
from datetime import datetime, timezone
import hmac

from ._errors import RelayedTimestampError, RelayedSignatureError

def verify_webhook(body: bytes,signature: str,timestamp: str,secret: str,tolerance_seconds: int = 300,) -> None:
    try:   
        timestamp_int = int(timestamp)
    except (ValueError, TypeError):
        raise RelayedTimestampError("Webhook timestamp is missing or invalid.")
    current_timestamp = int(datetime.now(timezone.utc).timestamp())
    if abs(current_timestamp - timestamp_int) > tolerance_seconds:
        raise RelayedTimestampError("Webhook timestamp is outside the allowed tolerance.")
    reconstructed_payload = str(timestamp_int).encode("utf-8") + b"." + body
    expected_signature = hmac.new(secret.encode(), reconstructed_payload, digestmod="sha256").hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        raise RelayedSignatureError("Webhook signature does not match the expected signature.")
    return None