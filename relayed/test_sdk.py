from relayed_sdk import Relayed
import os
from dotenv import load_dotenv, find_dotenv
from pathlib import Path

load_dotenv(find_dotenv(), override=False)
print(os.getenv("API_KEY"))
relayed = Relayed(os.getenv("API_KEY"), base_url="http://18.207.144.60")


response = relayed.send_event(
    destination_url="https://webhook.site/1a4b3201-2814-46b7-aa13-ababfa88b463",
    event_type="test.event",
    payload={"message": "Hello from the SDK", "source": "test_sdk.py"}
)

print(response.status_code, response.json())