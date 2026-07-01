import hmac
from datetime import datetime, timezone
from worker import sign_payload

def test_sign_payload_produces_verifiable_signature():
    secret = "test-secret"
    body = b'{"event": "test"}'
    timestamp = int(datetime.now(timezone.utc).timestamp())
    signature = sign_payload(secret=secret, body=body, timestamp=timestamp)
    expected_signed = str(timestamp).encode("utf-8") + b"." + body
    expected_sig = hmac.new(secret.encode(), expected_signed, "sha256").hexdigest()
    assert hmac.compare_digest(signature, expected_sig)