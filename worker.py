import redis
from dotenv import load_dotenv
import os
from uuid import UUID
from pathlib import Path
import httpx
from sqlalchemy import create_engine, select, update
from sqlmodel import Session
from database import Event
load_dotenv(Path(__file__).parent / ".env")


DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, echo=True)
r = redis.Redis(host='localhost', port=6379, decode_responses=True)


# Worker loop for processing events
while True:
    event = r.brpop("relay:events:pending", timeout=0)
    with Session(engine) as session:
        dbItem = session.exec(select(Event).where(Event.id == UUID(event[1]))).first()[0]
        payload = dbItem.payload
        destination_url = dbItem.destination_url
        
        try:
            response = httpx.post(destination_url, json=payload)
            print(response.status_code)
            print(response.json())

        #Update event status based on response
            if 200 <= response.status_code < 300:
                session.exec(update(Event).where(Event.id == UUID(event[1])).values(status='delivered'))
            else:
                session.exec(update(Event).where(Event.id == UUID(event[1])).values(status='failed'))
            session.commit()
        except Exception as e:
            print("Error sending event:", e)
            session.exec(update(Event).where(Event.id == event[1]).values(status='failed'))
            session.commit()

