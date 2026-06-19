import redis
from dotenv import load_dotenv
import time
from prometheus_client import start_http_server
import os
from uuid import UUID
from pathlib import Path
import httpx
from sqlalchemy import create_engine, select
from sqlmodel import Session
from database import Event, DeadLetter
import random
from datetime import datetime, timedelta
from metrics import DELIVERY_DURATION, RETRYING, DELIVERED, FAILED
import json
import hmac
load_dotenv(Path(__file__).parent / ".env", override=False)


DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, echo=True)
r = redis.Redis(host='redis', port=6379, decode_responses=True)


def retry(event : Event):
    if event.status != 'retrying':
        RETRYING.inc()
    #retry if failed initially
    event.attempts += 1
    event.status = 'retrying'
    print(f"RETRY called - metrics:retrying now: {event.attempts}")
    delay = (2 ** event.attempts) + random.uniform(0, 1)
    event.next_attempt_at = datetime.now() + timedelta(seconds=delay)
    r.lpush("relay:events:pending", str(event.id))


def worker():
# Worker loop for processing events
    start_http_server(8001)
    while True:
        try: 
            event = r.brpop("relay:events:pending", timeout=30)
            if event is None:
                continue
            with Session(engine) as session:
                dbItem = session.exec(select(Event).where(Event.id == UUID(event[1]))).first()[0]
                print(f"Processing event {dbItem.id}, status: {dbItem.status}, attempts: {dbItem.attempts}")
                payload = dbItem.payload
                destination_url = dbItem.destination_url
                
                if dbItem.next_attempt_at and datetime.now() < dbItem.next_attempt_at:
                    r.lpush("relay:events:pending", str(dbItem.id))
                    time.sleep(0.5)
                    continue
                
                try:
                    secret = os.getenv("SECRET").encode()
                    byte_data = json.dumps(payload).encode("utf-8")
                    signature = hmac.new(secret, byte_data, digestmod="sha256").hexdigest()
                    with DELIVERY_DURATION.time():
                        response = httpx.post(destination_url, content=byte_data, headers={"X-Relay-Signature" : signature, "Content-Type" : "application/json"})

                #Update event status based on response
                    if 200 <= response.status_code < 300:
                        was_retrying = dbItem.status == 'retrying'  # check BEFORE changing
                        dbItem.status = 'delivered'
                        session.add(dbItem)
                        session.commit()
                        DELIVERED.inc()
                        if was_retrying:
                            RETRYING.dec()
                    else:
                        if dbItem.attempts < 5:
                            retry(dbItem)  # handles status = 'retrying' and metrics:retrying increment
                            session.add(dbItem)
                            session.commit()
                        else:
                            was_retrying = dbItem.status == 'retrying'
                            dbItem.status = 'failed'
                            failure = DeadLetter(
                                event_id = dbItem.id,
                                attempts = dbItem.attempts,
                                status_code = response.status_code,
                                response_body = response.text,
                            )
                            session.add(dbItem)
                            session.add(failure)
                            session.commit()
                            FAILED.inc()
                            if was_retrying:
                                RETRYING.dec()
                except Exception as e:
                        print("Error sending event:", e)
                        if dbItem.attempts < 5:
                            retry(dbItem)
                            session.add(dbItem)
                            session.commit()
                        else:
                            was_retrying = dbItem.status == 'retrying'
                            dbItem.status = 'failed'
                            failure = DeadLetter(
                                event_id = dbItem.id,
                                attempts = dbItem.attempts,
                                error_message = str(e)
                            )
                            session.add(dbItem)
                            session.add(failure)
                            session.commit()
                            FAILED.inc()
                            if was_retrying:
                                RETRYING.dec()
        except redis.exceptions.TimeoutError:
            continue
        except redis.exceptions.ConnectionError:
            time.sleep(1)
            continue




def main():
    worker()

if __name__ == "__main__":
    main()