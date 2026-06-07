from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import redis
from database import Event, EventBase, engine, create_db_and_tables
from sqlmodel import Session, select
import uuid

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/v1/events")
async def create_event(event: EventBase):
    newEvent = Event(
        destination_url=event.destination_url,
        event_type=event.event_type,
        payload=event.payload,
    )
    with Session(engine) as session:
        session.add(newEvent)
        session.commit()
        session.refresh(newEvent)
    r.lpush("relay:events:pending", str(newEvent.id))
    return JSONResponse(status_code=202, content={"id": str(newEvent.id), "status": "queued"})

@app.get("/v1/events")
async def list_events():
    with Session(engine) as session:
        return session.exec(select(Event)).all()