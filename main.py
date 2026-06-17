from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, Response
from typing import Annotated
import redis
import secrets
from database import Event, EventBase, engine, create_db_and_tables
from sqlmodel import Session, select
from metrics import EVENTS, DELIVERED, FAILED, RETRYING
import uuid
import os
from prometheus_client import generate_latest,CONTENT_TYPE_LATEST

r = redis.Redis(host='redis', port=6379, decode_responses=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

security = HTTPBearer()

@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/v1/events")
async def create_event(event: EventBase, credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)], idempotency_key: Annotated[str, Header()]):
    current_API_key_bytes = credentials.credentials.encode("utf8")
    correct_API_key_bytes = os.getenv("API_KEY").encode("utf8")
    is_correct_api_key = secrets.compare_digest(current_API_key_bytes, correct_API_key_bytes)
    if not is_correct_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect API KEY",
            headers={"WWW-Authenticate": "Bearer"},
        )
    existing_event_id = r.get(f'idempotency:{idempotency_key}')
    if existing_event_id:
        with Session(engine) as session:
            existing_status = session.exec(select(Event.status).where(Event.id == existing_event_id)).first()
            return JSONResponse(status_code=202, content={"id": existing_event_id, "status": existing_status})
    newEvent = Event(
        destination_url=event.destination_url,
        event_type=event.event_type,
        payload=event.payload,
    )
    with Session(engine) as session:
        session.add(newEvent)
        session.commit()
        session.refresh(newEvent)
    r.set(f'idempotency:{idempotency_key}', str(newEvent.id), ex=86400)
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
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)