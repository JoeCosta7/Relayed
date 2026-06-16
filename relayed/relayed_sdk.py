import json
import httpx

class Relayed:

    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url

    def send_event(self, destination_url, event_type, payload):
        body = json.dumps({"destination_url" : destination_url, "event_type" : event_type, "payload" : payload})
        response = httpx.post(f'{self.base_url}/v1/events', content=body, headers={"Authorization" : f'Bearer {self.api_key}', "Content-Type": "application/json" })
        if not 200 <= response.status_code < 300:
            raise Exception(f"Relay returned {response.status_code}: {response.text}")
        return response
        