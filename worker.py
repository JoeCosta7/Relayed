import redis
from dotenv import load_dotenv
import time
from prometheus_client import start_http_server
import os
from uuid import UUID
from pathlib import Path
import httpx
from sqlalchemy import create_engine
from sqlmodel import Session, select
from database import Event, DeadLetter, Customer, Delivery, Subscription, SubscriptionStatusEnum, DeliveryStatusEnum
import random
from datetime import datetime, timedelta, timezone
from worker_metrics import DELIVERY_DURATION, RETRYING, DELIVERED, FAILED
import json
import hmac
load_dotenv(Path(__file__).parent / ".env", override=False)


DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, echo=True)
redis_host = os.getenv("REDIS_HOST", "redis")
redis_port = int(os.getenv("REDIS_PORT", "6379"))
r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)

def sign_payload(secret: str, body: bytes, timestamp: int) -> str:
    signed_payload = str(timestamp).encode("utf-8") + b"." + body
    return hmac.new(secret.encode(), signed_payload, digestmod="sha256").hexdigest()


def retry(delivery : Delivery):
    if delivery.status != DeliveryStatusEnum.RETRYING:
        RETRYING.inc()
    #retry if failed initially
    delivery.attempts += 1
    delivery.status = DeliveryStatusEnum.RETRYING
    print(f"RETRY called - metrics:retrying now: {delivery.attempts}")
    delay = (2 ** delivery.attempts) + random.uniform(0, 1)
    delivery.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
    r.lpush("relay:deliveries:pending", str(delivery.id))

def process_delivery(delivery_id_str : str):
    with Session(engine) as session:
        deliveryItem = session.exec(select(Delivery).where(Delivery.id == UUID(delivery_id_str))).first()
        if deliveryItem is None:
            print(f"Event {delivery_id_str} not found — skipping")
            return
        customer = session.exec(select(Customer).where(Customer.id == deliveryItem.customer_id)).first()
        if customer is None:
            print(f"Event {deliveryItem.id} has no customer — skipping")
            return
        subscription = session.exec(select(Subscription).where(deliveryItem.subscription_id == Subscription.id)).first()
        if subscription is None or subscription.status == SubscriptionStatusEnum.DISABLED:
            print(f"Event {deliveryItem.id} has no subscription — skipping")
            return
        destination_url = subscription.destination_url
        event = session.exec(select(Event).where(Event.id == deliveryItem.event_id)).first()
        if event is None:
            print(f"Event {deliveryItem.id} has no event — skipping")
            return
        print(f"Processing event {deliveryItem.id}, status: {deliveryItem.status}, attempts: {deliveryItem.attempts}")
        payload = event.payload
        if deliveryItem.next_attempt_at and datetime.now(timezone.utc) < deliveryItem.next_attempt_at:
            r.lpush("relay:deliveries:pending", str(delivery_id_str))
            time.sleep(0.5)
            return
        try:
            byte_data = json.dumps(payload).encode("utf-8")
            timestamp_int = int(datetime.now(timezone.utc).timestamp())
            signature = sign_payload(secret=subscription.webhook_secret,body=byte_data,timestamp=timestamp_int)
            with DELIVERY_DURATION.time():
                response = httpx.post(destination_url, content=byte_data, headers={"X-Relay-Signature" : signature, "X-Relay-Timestamp": str(timestamp_int), "Content-Type" : "application/json"})
            #Update event status based on response
            if 200 <= response.status_code < 300:
                was_retrying = deliveryItem.status == DeliveryStatusEnum.RETRYING  # check BEFORE changing
                deliveryItem.status = DeliveryStatusEnum.DELIVERED
                session.add(deliveryItem)
                session.commit()
                DELIVERED.inc()
                if was_retrying:
                    RETRYING.dec()
            else:
                if deliveryItem.attempts < 5:
                    retry(deliveryItem)  # handles status = 'retrying' and metrics:retrying increment
                    session.add(deliveryItem)
                    session.commit()
                else:
                    was_retrying = deliveryItem.status == DeliveryStatusEnum.RETRYING
                    deliveryItem.status = DeliveryStatusEnum.DEAD_LETTERED
                    failure = DeadLetter(
                        event_id = event.id,
                        attempts = deliveryItem.attempts,
                        status_code = response.status_code,
                        response_body = response.text,
                        customer_id = event.customer_id,
                        subscription_id=subscription.id,
                        delivery_id = deliveryItem.id
                    )
                    session.add(deliveryItem)
                    session.add(failure)
                    session.commit()
                    FAILED.inc()
                    if was_retrying:
                        RETRYING.dec()
        except Exception as e:
                print("Error sending event:", e)
                if deliveryItem.attempts < 5:
                    retry(deliveryItem)
                    session.add(deliveryItem)
                    session.commit()
                else:
                    was_retrying = deliveryItem.status == DeliveryStatusEnum.RETRYING
                    deliveryItem.status = DeliveryStatusEnum.DEAD_LETTERED
                    failure = DeadLetter(
                        event_id = event.id,
                        attempts = deliveryItem.attempts,
                        error_message = str(e),
                        customer_id = event.customer_id,
                        subscription_id=subscription.id,
                        delivery_id = deliveryItem.id
                    )
                    session.add(deliveryItem)
                    session.add(failure)
                    session.commit()
                    FAILED.inc()
                    if was_retrying:
                        RETRYING.dec()


def worker():
    start_http_server(8001)
    while True:
        try:
            event = r.brpop("relay:deliveries:pending", timeout=30)
            if event is None:
                continue
            try:
                process_delivery(event[1])
            except Exception as e:
                print(f"Failed processing delivery {event[1]}: {e}")
                # don't re-enqueue, don't crash — just log and continue
        except redis.exceptions.TimeoutError:
            continue
        except redis.exceptions.ConnectionError:
            time.sleep(1)
            continue




def main():
    worker()

if __name__ == "__main__":
    main()