# Relayed

A Python Client for Relayed, a Webhooks Delivery Service.

## Installation

```bash
pip install relayed
```

## Quick start

```python
import uuid
from relayed import RelayedClient, RelayedClientError

client = RelayedClient(
    api_key="your-api-key",
    base_url="https://relayed.example.com",
    )

subscription = client.create_subscription(
        destination_url="https://example.com",
        event_types=["invoice.paid", "invoice.unpaid"],
        description="Subscription for a contractor to send webhook whether customer paid the invoice"
    )
try:
    response = client.send_event(
        event_type="invoice.paid",
        payload={"invoice_id": "inv_123", "amount": 4200},
        idempotency_key=str(uuid.uuid4()),  # use a stable value across retries
    )
    print(response)  # {"event_id": "...", "delivery_ids": [...]}
except RelayedClientError as e:
    print(f"Cannot send event: {e}")

```

## Error Handling

All errors raised by the SDK inherit from RelayedError, so you can catch everything with a single except clause, or catch specific subclasses for fine-grained handling.

```python
from relayed import (
    RelayedError,
    RelayedAuthError,
    RelayedNotFoundError,
    RelayedConflictError,
    RelayedClientError,
    RelayedServerError,
)
```

## Links

- Source: [Github URL](https://github.com/JoeCosta7/Relayed)
- Issues: [GitHub issues URL](https://github.com/JoeCosta7/Relayed/issues)