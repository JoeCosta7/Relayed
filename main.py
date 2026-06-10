from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
import redis
from database import Event, EventBase, engine, create_db_and_tables
from sqlmodel import Session, select
from metrics import EVENTS, DELIVERED, FAILED, LAST_DELIVERY_DURATION, RETRYING
import uuid
from prometheus_client import generate_latest,CONTENT_TYPE_LATEST

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
    EVENTS.inc()
    return JSONResponse(status_code=202, content={"id": str(newEvent.id), "status": "queued"})

@app.get("/v1/events")
async def list_events():
    with Session(engine) as session:
        return session.exec(select(Event)).all()

@app.get("/metrics")
async def get_metrics():
    DELIVERED.set(int(r.get('metrics:delivered') or 0))
    FAILED.set(int(r.get('metrics:failed') or 0))
    RETRYING.set(int(r.get('metrics:retrying') or 0))
    LAST_DELIVERY_DURATION.set(float(r.get('metrics:last_delivery_duration') or 0))
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)