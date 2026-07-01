import hmac
from datetime import datetime, timezone

import pytest

from relayed._webhooks import verify_webhook
from relayed import RelayedSignatureError, RelayedTimestampError


def _sign(body: bytes, timestamp: int, secret: str) -> str:
    """Produce the signature the worker would produce for this timestamp+body."""
    signed_payload = str(timestamp).encode("utf-8") + b"." + body
    return hmac.new(secret.encode(), signed_payload, digestmod="sha256").hexdigest()


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


SECRET = "test-webhook-secret"


def test_verify_webhook_happy_path():
    """A correctly-signed webhook with a fresh timestamp verifies without raising."""
    body = b'{"event": "delivery.succeeded"}'
    timestamp = _now()
    signature = _sign(body, timestamp, SECRET)
    assert verify_webhook(body, signature, str(timestamp), SECRET) is None


@pytest.mark.parametrize("bad_timestamp", ["", "abc", "1234abc", None])
def test_verify_webhook_invalid_timestamp_format(bad_timestamp):
    """Malformed timestamp values raise RelayedTimestampError."""
    body = b'{"event": "delivery.succeeded"}'
    with pytest.raises(RelayedTimestampError):
        verify_webhook(body, "0" * 64, bad_timestamp, SECRET)


def test_verify_webhook_timestamp_too_old():
    """A timestamp more than tolerance_seconds in the past raises RelayedTimestampError."""
    body = b'{"event": "delivery.succeeded"}'
    timestamp = _now() - 400
    signature = _sign(body, timestamp, SECRET)
    with pytest.raises(RelayedTimestampError):
        verify_webhook(body, signature, str(timestamp), SECRET)


def test_verify_webhook_timestamp_too_new():
    """A timestamp more than tolerance_seconds in the future raises RelayedTimestampError."""
    body = b'{"event": "delivery.succeeded"}'
    timestamp = _now() + 400
    signature = _sign(body, timestamp, SECRET)
    with pytest.raises(RelayedTimestampError):
        verify_webhook(body, signature, str(timestamp), SECRET)


def test_verify_webhook_bad_signature():
    """A well-formed but incorrect signature raises RelayedSignatureError."""
    body = b'{"event": "delivery.succeeded"}'
    timestamp = _now()
    with pytest.raises(RelayedSignatureError):
        verify_webhook(body, "0" * 64, str(timestamp), SECRET)