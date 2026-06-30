# import uuid

# from relayed.sdk.src.relayed.relayed_sdk import RelayedClient
# import os
# from dotenv import load_dotenv, find_dotenv
# from pathlib import Path

# load_dotenv(find_dotenv(), override=False)
# relayed = RelayedClient(os.getenv("API_KEY"), base_url="http://localhost:8000")

# subscription = relayed.create_subscription(
#     destination_url="https://webhook.site/1a4b3201-2814-46b7-aa13-ababfa88b463",
#     event_types=["test.event"],
# )
# print("subscription:", subscription["id"], "webhook_secret:", subscription["webhook_secret"])

# result = relayed.send_event(
#     event_type="test.event",
#     payload={"message": "Hello from the SDK", "source": "test_sdk.py"},
#     idempotency_key=str(uuid.uuid4()),
# )

# print("event:", result["event_id"], "deliveries:", result["delivery_ids"])