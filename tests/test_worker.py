import respx
import httpx
from sqlmodel import Session
from main import engine
from sqlmodel import Session, select 
from database import Event, DeadLetter, Delivery, DeliveryStatusEnum
from worker import process_delivery

@respx.mock
def test_successful_delivery(test_customer, test_subscription):
    respx.post(test_subscription.destination_url).mock(return_value=httpx.Response(200))

    with Session(engine) as session:
        event = Event(event_type="test", payload={}, customer_id=test_customer["customer"].id)
        session.add(event)
        session.flush()  # populates event.id
        delivery = Delivery(customer_id=test_customer["customer"].id,subscription_id=test_subscription.id,event_id=event.id, status="pending", attempts=0)
        session.add(delivery)
        session.commit()
        session.refresh(delivery)
        delivery_id = delivery.id

    process_delivery(str(delivery_id))

    with Session(engine) as session:
        updated_delivery = session.get(Delivery, delivery_id)
        assert updated_delivery.status == DeliveryStatusEnum.DELIVERED


@respx.mock
def test_failed_delivery_under_attempt_limit(test_customer, test_subscription):
    respx.post(test_subscription.destination_url).mock(return_value=httpx.Response(500, text="Server Error"))

    with Session(engine) as session:
        event = Event(event_type="test", payload={}, customer_id=test_customer["customer"].id)
        session.add(event)
        session.flush()  # populates event.id
        delivery = Delivery(customer_id=test_customer["customer"].id,subscription_id=test_subscription.id,event_id=event.id, status="pending", attempts=0)
        session.add(delivery)
        session.commit()
        session.refresh(delivery)
        delivery_id = delivery.id

    process_delivery(str(delivery_id))

    with Session(engine) as session:
        updated_delivery = session.get(Delivery, delivery_id)
        assert updated_delivery.status == DeliveryStatusEnum.RETRYING
        assert updated_delivery.attempts == 1
        assert updated_delivery.next_attempt_at is not None
        dl = session.exec(select(DeadLetter).where(DeadLetter.delivery_id == delivery_id)).first() 
        assert dl is None

@respx.mock
def test_failed_delivery_over_attempt_limit(test_customer, test_subscription):
    respx.post(test_subscription.destination_url).mock(return_value=httpx.Response(500, text="Server Error"))

    with Session(engine) as session:
        event = Event(event_type="test", payload={}, customer_id=test_customer["customer"].id)
        session.add(event)
        session.flush()  # populates event.id
        delivery = Delivery(customer_id=test_customer["customer"].id,subscription_id=test_subscription.id,event_id=event.id, status="retrying", attempts=5)
        session.add(delivery)
        session.commit()
        session.refresh(delivery)
        delivery_id = delivery.id

    process_delivery(str(delivery_id))
    
    
    with Session(engine) as session:
        updated_delivery = session.get(Delivery, delivery_id)
        assert updated_delivery.status == DeliveryStatusEnum.DEAD_LETTERED
        dl = session.exec(select(DeadLetter).where(DeadLetter.delivery_id == delivery_id)).first() 
        assert dl is not None
        assert dl.status_code == 500
        assert dl.response_body == "Server Error"

@respx.mock
def test_exception_during_delivery_under_attempt_limit(test_customer, test_subscription):
    respx.post(test_subscription.destination_url).mock(side_effect=httpx.ConnectError("Connection Refused"))

    with Session(engine) as session:
        event = Event(event_type="test", payload={}, customer_id=test_customer["customer"].id)
        session.add(event)
        session.flush()  # populates event.id
        delivery = Delivery(customer_id=test_customer["customer"].id,subscription_id=test_subscription.id,event_id=event.id, status="pending", attempts=0)
        session.add(delivery)
        session.commit()
        session.refresh(delivery)
        delivery_id = delivery.id

    process_delivery(str(delivery_id))
    
    
    with Session(engine) as session:
        updated_delivery = session.get(Delivery, delivery_id)
        assert updated_delivery.status == DeliveryStatusEnum.RETRYING
        assert updated_delivery.attempts == 1
        assert updated_delivery.next_attempt_at is not None
        dl = session.exec(select(DeadLetter).where(DeadLetter.delivery_id == delivery_id)).first() 
        assert dl is None

@respx.mock
def test_exception_during_delivery_over_attempt_limit(test_customer, test_subscription):
    respx.post(test_subscription.destination_url).mock(side_effect=httpx.ConnectError("Connection Refused"))

    with Session(engine) as session:
        event = Event(event_type="test", payload={}, customer_id=test_customer["customer"].id)
        session.add(event)
        session.flush()  # populates event.id
        delivery = Delivery(customer_id=test_customer["customer"].id,subscription_id=test_subscription.id,event_id=event.id, status="retrying", attempts=5)
        session.add(delivery)
        session.commit()
        session.refresh(delivery)
        delivery_id = delivery.id

    process_delivery(str(delivery_id))
    
    
    with Session(engine) as session:
        updated_delivery = session.get(Delivery, delivery_id)
        assert updated_delivery.status == DeliveryStatusEnum.DEAD_LETTERED
        dl = session.exec(select(DeadLetter).where(DeadLetter.delivery_id == delivery_id)).first() 
        assert dl is not None
        assert dl.error_message == "Connection Refused"
        assert dl.response_body is None
        assert dl.status_code is None

