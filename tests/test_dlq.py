from fastapi.testclient import TestClient
from database import Event, DeadLetter, engine, Delivery, DeliveryStatusEnum
from sqlmodel import Session
from uuid import uuid4, UUID
from datetime import datetime, timezone
from main import app


client = TestClient(app)

def test_filter_replayed_entries(test_customer, test_subscription):
    api_key = test_customer["api_key"]
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    with Session(engine) as session:
        event1 = Event(event_type="test", payload={}, customer_id = test_customer["customer"].id)
        session.add(event1)
        session.commit()
        session.refresh(event1)

        delivery1 = Delivery(event_id=event1.id, customer_id=test_customer["customer"].id, 
                             subscription_id=test_subscription.id, status=DeliveryStatusEnum.DEAD_LETTERED, attempts=5)
        session.add(delivery1)
        session.commit()
        session.refresh(delivery1)
        
        dl1 = DeadLetter(event_id=event1.id, attempts=5, status_code=500, replayed_at=datetime.now(timezone.utc), 
                        customer_id = test_customer["customer"].id, subscription_id=test_subscription.id, delivery_id = delivery1.id)
        session.add(dl1)
        session.commit()
        session.refresh(dl1)

        event2 = Event(event_type="test", payload={}, customer_id = test_customer["customer"].id)
        
        session.add(event2)
        session.commit()
        session.refresh(event2)

        delivery2 = Delivery(event_id=event2.id, customer_id=test_customer["customer"].id, 
                             subscription_id=test_subscription.id, status=DeliveryStatusEnum.DEAD_LETTERED, attempts=5)
        session.add(delivery2)
        session.commit()
        session.refresh(delivery2)
        
        dl2 = DeadLetter(event_id=event2.id, attempts=5, status_code=500, replayed_at=None, 
                        customer_id = test_customer["customer"].id, subscription_id=test_subscription.id, delivery_id = delivery2.id)
        session.add(dl2)
        session.commit()
        session.refresh(dl2)

        response = client.get(f"/v1/deadletter", headers=auth_headers)
        assert response.status_code == 200
        ids_in_response = {entry["id"] for entry in response.json()}
        assert str(dl2.id) in ids_in_response
        assert str(dl1.id) not in ids_in_response



def test_replay_endpoint_resets_state(test_customer, test_subscription):
    api_key = test_customer["api_key"]
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    with Session(engine) as session:
        event = Event(event_type="test", payload={}, customer_id = test_customer["customer"].id)
        session.add(event)
        session.commit()
        session.refresh(event)

        delivery = Delivery(event_id=event.id, customer_id=test_customer["customer"].id, subscription_id=test_subscription.id, status=DeliveryStatusEnum.DEAD_LETTERED, attempts=5)
        session.add(delivery)
        session.commit()
        session.refresh(delivery)
            
        dl = DeadLetter(event_id=event.id, attempts=5, status_code=500, replayed_at=None, 
                        customer_id = test_customer["customer"].id, subscription_id=test_subscription.id, delivery_id = delivery.id)
        session.add(dl)
        session.commit()
        session.refresh(dl)
        delivery_id, dl_id = delivery.id, dl.id 

        response = client.post(f"/v1/deadletter/{dl_id}/replay", headers=auth_headers)
        assert response.status_code == 202
        new_delivery_id = response.json()["delivery_ids"][0]  #
        assert new_delivery_id != str(delivery_id) 

        with Session(engine) as session:
            new_delivery = session.get(Delivery, UUID(new_delivery_id))
            assert new_delivery.status == DeliveryStatusEnum.PENDING
            assert new_delivery.attempts == 0

            updated_dl = session.get(DeadLetter, dl_id)
            assert updated_dl.replayed_at is not None 

def test_replay_nonexistent_dl_returns_404(test_customer):
    api_key = test_customer["api_key"]
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    nonexistent_id = uuid4()
    response = client.post(f"/v1/deadletter/{nonexistent_id}/replay", headers=auth_headers)
    assert response.status_code == 404

def test_replay_already_replayed_returns_409(test_customer, test_subscription):
    api_key = test_customer["api_key"]
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    with Session(engine) as session:
        event = Event(event_type="test", payload={}, customer_id = test_customer["customer"].id)
        
        session.add(event)
        session.commit()
        session.refresh(event)

        delivery = Delivery(event_id=event.id, customer_id=test_customer["customer"].id, subscription_id=test_subscription.id, status=DeliveryStatusEnum.DEAD_LETTERED, attempts=5)
        session.add(delivery)
        session.commit()
        session.refresh(delivery)
            
        dl = DeadLetter(event_id=event.id, attempts=5, status_code=500, replayed_at=datetime.now(timezone.utc), 
                        customer_id = test_customer["customer"].id, subscription_id=test_subscription.id, delivery_id = delivery.id)
        session.add(dl)
        session.commit()
        session.refresh(dl)
        dl_id = dl.id 

    response = client.post(f"/v1/deadletter/{dl_id}/replay", headers=auth_headers)
    assert response.status_code == 409



