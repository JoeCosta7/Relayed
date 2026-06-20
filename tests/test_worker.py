import respx
import httpx
from sqlmodel import Session
from main import engine
from sqlmodel import Session, select 
from database import Event, DeadLetter
from worker import process_event

@respx.mock
def test_successful_delivery():
    respx.post("https://example.com/webhook").mock(return_value=httpx.Response(200))

    with Session(engine) as session:
        event = Event(destination_url="https://example.com/webhook", event_type="test", payload={}, status="pending", attempts=0)
        session.add(event)
        session.commit()
        session.refresh(event)
        event_id = event.id

    process_event(str(event_id))

    with Session(engine) as session:
        updated_event = session.get(Event, event_id)
        assert updated_event.status == "delivered"

@respx.mock
def test_failed_delivery_under_attempt_limit():
    respx.post("https://example.com/webhook").mock(return_value=httpx.Response(500, text="Server Error"))

    with Session(engine) as session:
        event = Event(destination_url="https://example.com/webhook", event_type="test", payload={}, status="pending", attempts=0)
        session.add(event)
        session.commit()
        session.refresh(event)
        event_id = event.id

    process_event(str(event_id))
    
    
    with Session(engine) as session:
        updated_event = session.get(Event, event_id)
        assert updated_event.status == "retrying"
        assert updated_event.attempts == 1
        assert updated_event.next_attempt_at is not None
        dl = session.exec(select(DeadLetter).where(DeadLetter.event_id == event_id)).first() 
        assert dl is None

@respx.mock
def test_failed_delivery_over_attempt_limit():
    respx.post("https://example.com/webhook").mock(return_value=httpx.Response(500, text="Server Error"))

    with Session(engine) as session:
        event = Event(destination_url="https://example.com/webhook", event_type="test", payload={}, status="retrying", attempts=5)
        session.add(event)
        session.commit()
        session.refresh(event)
        event_id = event.id

    process_event(str(event_id))
    
    
    with Session(engine) as session:
        updated_event = session.get(Event, event_id)
        assert updated_event.status == "failed"
        dl = session.exec(select(DeadLetter).where(DeadLetter.event_id == event_id)).first() 
        assert dl is not None
        assert dl.status_code == 500
        assert dl.response_body == "Server Error"

@respx.mock
def test_exception_during_delivery_under_attempt_limit():
    respx.post("https://example.com/webhook").mock(side_effect=httpx.ConnectError("Connection Refused"))

    with Session(engine) as session:
        event = Event(destination_url="https://example.com/webhook", event_type="test", payload={}, status="pending", attempts=0)
        session.add(event)
        session.commit()
        session.refresh(event)
        event_id = event.id

    process_event(str(event_id))
    
    
    with Session(engine) as session:
        updated_event = session.get(Event, event_id)
        assert updated_event.status == "retrying"
        assert updated_event.attempts == 1
        assert updated_event.next_attempt_at is not None
        dl = session.exec(select(DeadLetter).where(DeadLetter.event_id == event_id)).first() 
        assert dl is None

@respx.mock
def test_exception_during_delivery_over_attempt_limit():
    respx.post("https://example.com/webhook").mock(side_effect=httpx.ConnectError("Connection Refused"))

    with Session(engine) as session:
        event = Event(destination_url="https://example.com/webhook", event_type="test", payload={}, status="retrying", attempts=5)
        session.add(event)
        session.commit()
        session.refresh(event)
        event_id = event.id

    process_event(str(event_id))
    
    
    with Session(engine) as session:
        updated_event = session.get(Event, event_id)
        assert updated_event.status == "failed"
        dl = session.exec(select(DeadLetter).where(DeadLetter.event_id == event_id)).first() 
        assert dl is not None
        assert dl.error_message == "Connection Refused"
        assert dl.response_body is None
        assert dl.status_code is None

