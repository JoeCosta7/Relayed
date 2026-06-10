import redis
from dotenv import load_dotenv
import time
import os
from uuid import UUID
from pathlib import Path
import httpx
from sqlalchemy import create_engine, select, update
from sqlmodel import Session
from database import Event
import random
from datetime import datetime, timedelta
from metrics import DELIVERED, FAILED, RETRYING, LAST_DELIVERY_DURATION
load_dotenv(Path(__file__).parent / ".env")


DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, echo=True)
r = redis.Redis(host='localhost', port=6379, decode_responses=True)


def retry(event : Event):
    #retry if failed initially
    event.attempts += 1
    event.status = 'retrying'
    result = r.incr('metrics:retrying')
    print(f"RETRY called - metrics:retrying now: {result}")
    delay = 1 * (2 ** event.attempts) + random.uniform(0, 1)
    event.next_attempt_at = datetime.now() + timedelta(seconds=delay)
    r.lpush("relay:events:pending", str(event.id))
    result = r.decr('metrics:retrying')

def worker():
# Worker loop for processing events
    while True:
        event = r.brpop("relay:events:pending", timeout=0)
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
                start = time.time()
                response = httpx.post(destination_url, json=payload)
                duration = time.time() - start
                r.set('metrics:last_delivery_duration', duration)

            #Update event status based on response
                if 200 <= response.status_code < 300:
                    was_retrying = dbItem.status == 'retrying'  # check BEFORE changing
                    dbItem.status = 'delivered'
                    session.add(dbItem)
                    session.commit()
                    r.incr('metrics:delivered')
                    if was_retrying:
                        r.decr('metrics:retrying')
                else:
                    if dbItem.attempts < 5:
                        retry(dbItem)  # handles status = 'retrying' and metrics:retrying increment
                        session.add(dbItem)
                        session.commit()
                    else:
                        was_retrying = dbItem.status == 'retrying'
                        dbItem.status = 'failed'
                        session.add(dbItem)
                        session.commit()
                        r.incr('metrics:failed')
                        if was_retrying:
                            r.decr('metrics:retrying')
            except Exception as e:
                    print("Error sending event:", e)
                    if dbItem.attempts < 5:
                        retry(dbItem)
                        session.add(dbItem)
                        session.commit()
                    else:
                        was_retrying = dbItem.status == 'retrying'
                        dbItem.status = 'failed'
                        session.add(dbItem)
                        session.commit()
                        r.incr('metrics:failed')
                        if was_retrying:
                            r.decr('metrics:retrying')


def main():
    worker()

if __name__ == "__main__":
    main()