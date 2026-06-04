from sqlmodel import Field, SQLModel, create_engine, Session, select
import os
from typing import Dict, Any
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.dialects.postgresql import JSONB
from uuid import UUID, uuid4
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

class EventBase(SQLModel):
    destination_url: str
    event_type: str
    payload: Dict[str, Any] = Field(default={}, sa_type=JSONB)
    status: str

class Event(EventBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)


engine = create_engine(DATABASE_URL, echo=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/v1/events")
async def create_event(event: EventBase):
    newEvent = Event(
        destination_url=event.destination_url,
        event_type=event.event_type,
        payload=event.payload,
        status="pending"
    )
    with Session(engine) as session:
        session.add(newEvent)
        session.commit()
        session.refresh(newEvent)

    return JSONResponse(status_code=202, content={"id": str(newEvent.id), "status": "queued"})

@app.get("/v1/events")
async def list_events():
    with Session(engine) as session:
        return session.exec(select(Event)).all()

if __name__ == "__main__":
    create_db_and_tables()
