from fastapi.testclient import TestClient
from database import Event, DeadLetter, engine
from sqlmodel import Session
import os
import uuid
from datetime import datetime
from main import app
from main import r

client = TestClient(app)
api_key = os.getenv("API_KEY")
auth_headers = {"Authorization": f"Bearer {api_key}"}


def test_filter_replayed_entries():
    with Session(engine) as session:
        event1 = Event(destination_url="...", event_type="test", payload={}, status="failed", attempts=5)
        session.add(event1)
        session.commit()
        session.refresh(event1)
        
        dl1 = DeadLetter(event_id=event1.id, attempts=5, status_code=500, replayed_at=datetime.now())
        session.add(dl1)
        session.commit()
        session.refresh(dl1)

        event2 = Event(destination_url="...", event_type="test", payload={}, status="failed", attempts=5)
        session.add(event2)
        session.commit()
        session.refresh(event2)
        
        dl2 = DeadLetter(event_id=event2.id, attempts=5, status_code=500, replayed_at=None)
        session.add(dl2)
        session.commit()
        session.refresh(dl2)

        response = client.get(f"/v1/deadletter", headers=auth_headers)
        assert response.status_code == 200
        ids_in_response = {entry["id"] for entry in response.json()}
        assert str(dl2.id) in ids_in_response
        assert str(dl1.id) not in ids_in_response



def test_replay_endpoint_resets_state():
    with Session(engine) as session:
        event = Event(destination_url="...", event_type="test", payload={}, status="failed", attempts=5)
        session.add(event)
        session.commit()
        session.refresh(event)
            
        dl = DeadLetter(event_id=event.id, attempts=5, status_code=500, replayed_at=None)
        session.add(dl)
        session.commit()
        session.refresh(dl)
        event_id, dl_id = event.id, dl.id 

        response = client.post(f"/v1/deadletter/{dl_id}/replay", headers=auth_headers)
        assert response.status_code == 200

        with Session(engine) as session:
            updated_event = session.get(Event, event_id)
            assert updated_event.status == "pending"
            assert updated_event.attempts == 0

            updated_dl = session.get(DeadLetter, dl_id)
            assert updated_dl.replayed_at is not None 
        



