from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, Response
from typing import Annotated
import redis
import secrets
from database import Event, EventBase, DeadLetter, engine, create_db_and_tables
from sqlmodel import Session, select
from metrics import EVENTS
import os
from uuid import UUID
from datetime import datetime
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

async def verify_api_key(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    current_API_key_bytes = credentials.credentials.encode("utf8")
    correct_API_key_bytes = os.getenv("API_KEY").encode("utf8")
    is_correct_api_key = secrets.compare_digest(current_API_key_bytes, correct_API_key_bytes)
    if not is_correct_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect API KEY",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.post("/v1/events")
async def create_event(event: EventBase, _: Annotated[None, Depends(verify_api_key)], idempotency_key: Annotated[str, Header()]):
    
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
        claimed = r.set(f'idempotency:{idempotency_key}', str(newEvent.id), ex=86400, nx=True)
        # winner branch
        if claimed:  
            r.lpush("relay:events:pending", str(newEvent.id))
            EVENTS.inc()
            return JSONResponse(status_code=202, content={"id": str(newEvent.id), "status": "queued"})
        #loser branch
        else: 
            session.delete(newEvent)
            session.commit()
            winner = r.get(f'idempotency:{idempotency_key}')
            current_status = session.exec(select(Event.status).where(Event.id == winner)).first()
            return JSONResponse(status_code=202, content={"id": winner, "status": current_status})

@app.get("/v1/events")
async def list_events(_: Annotated[None, Depends(verify_api_key)]):
    with Session(engine) as session:
        return session.exec(select(Event)).all()


@app.get("/v1/deadletter")
async def list_dead_letter_events(_: Annotated[None, Depends(verify_api_key)]):
    with Session(engine) as session:
        #finds ones that haven't been resolved
        return session.exec(select(DeadLetter).where(DeadLetter.replayed_at == None)).all()

@app.post("/v1/deadletter/{dl_id}/replay")
async def replay_dead_letter(dl_id: UUID, _: Annotated[None, Depends(verify_api_key)]):
    with Session(engine) as session:
        deadletter = session.exec(select(DeadLetter).where(DeadLetter.id == dl_id)).first()
        associated_event = session.exec(select(Event).where(Event.id == deadletter.event_id)).first()
        associated_event.status = 'pending'
        associated_event.attempts = 0
        associated_event.next_attempt_at = None
        deadletter.replayed_at = datetime.now()
        session.commit()
        r.lpush("relay:events:pending", str(associated_event.id))
        return f'Retrying event {associated_event.id}'

@app.get("/metrics")
async def get_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)