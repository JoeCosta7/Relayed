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
load_dotenv(Path(__file__).parent / ".env")


DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, echo=True)
r = redis.Redis(host='localhost', port=6379, decode_responses=True)


def retry(event : Event):
    #retry if failed initially
    event.attempts += 1
    event.status = 'retrying'
    delay = 1 * (2 ** event.attempts) + random.uniform(0, 1)
    event.next_attempt_at = datetime.now() + timedelta(seconds=delay)
    r.lpush("relay:events:pending", str(event.id))
    



def worker():
# Worker loop for processing events
    while True:
        event = r.brpop("relay:events:pending", timeout=0)
        with Session(engine) as session:
            dbItem = session.exec(select(Event).where(Event.id == UUID(event[1]))).first()[0]
            payload = dbItem.payload
            destination_url = dbItem.destination_url
            
            if dbItem.next_attempt_at and datetime.now() < dbItem.next_attempt_at:
                r.lpush("relay:events:pending", str(dbItem.id))
                time.sleep(0.5)
                continue
            
            try:
                response = httpx.post(destination_url, json=payload)

            #Update event status based on response
                if 200 <= response.status_code < 300:
                    session.exec(update(Event).where(Event.id == UUID(event[1])).values(status='delivered'))
                else:
                    session.exec(update(Event).where(Event.id == UUID(event[1])).values(status='failed'))
                    if dbItem.attempts < 5:
                        retry(dbItem)
                        dbItem.status = 'delivered'
                        session.add(dbItem)
                        session.commit()
                    else:
                        session.exec(update(Event).where(Event.id == UUID(event[1])).values(status='failed'))
                        session.commit()
            except Exception as e:
                print("Error sending event:", e)
                session.exec(update(Event).where(Event.id == event[1]).values(status='failed'))
                if dbItem.attempts < 5:
                    retry(dbItem)
                    dbItem.status = 'delivered'
                    session.add(dbItem)
                    session.commit()
                else:
                    session.exec(update(Event).where(Event.id == UUID(event[1])).values(status='failed'))
                    session.commit()
 


def main():
    worker()

if __name__ == "__main__":
    main()