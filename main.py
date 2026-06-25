from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, Response
from typing import Annotated
import redis
import secrets
from database import Event, EventBase, DeadLetter, Customer, CustomerCreated, CustomerCreate, engine, create_db_and_tables
from sqlmodel import Session, select
from app_metrics import EVENTS
import os
from uuid import UUID
from datetime import datetime
import hashlib
from prometheus_client import generate_latest,CONTENT_TYPE_LATEST

redis_host = os.getenv("REDIS_HOST", "redis")
redis_port = int(os.getenv("REDIS_PORT", "6379"))
r = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)

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
    with Session(engine) as session:
        incoming_hash = hashlib.sha256(credentials.credentials.encode("utf8")).hexdigest()
        customer = session.exec(select(Customer).where(Customer.api_key_hash == incoming_hash)).first()
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect API KEY",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return customer


async def verify_admin_key(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    incoming_admin_key_bytes = credentials.credentials.encode("utf8")
    correct_admin_key = os.getenv("ADMIN_API_KEY")
    if not correct_admin_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_API_KEY not configured",
        )
    correct_admin_key_bytes = correct_admin_key.encode("utf8")
    is_correct_admin_hash = secrets.compare_digest(incoming_admin_key_bytes, correct_admin_key_bytes)
    if not is_correct_admin_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect API KEY",
            headers={"WWW-Authenticate": "Bearer"},
        )



@app.post("/v1/events")
async def create_event(event: EventBase, current_customer: Annotated[Customer, Depends(verify_api_key)], idempotency_key: Annotated[str, Header()]):
    
    existing_event_id = r.get(f'idempotency:{idempotency_key}')
    if existing_event_id:
        with Session(engine) as session:
            existing_status = session.exec(select(Event.status).where(Event.id == existing_event_id)).first()
            return JSONResponse(status_code=202, content={"id": existing_event_id, "status": existing_status})
    newEvent = Event(
        destination_url=event.destination_url,
        event_type=event.event_type,
        payload=event.payload,
        customer_id = current_customer.id
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
async def list_events(current_customer: Annotated[None, Depends(verify_api_key)]):
    with Session(engine) as session:
        return session.exec(select(Event).where(Event.customer_id == current_customer.id)).all()


@app.get("/v1/deadletter")
async def list_dead_letter_events(current_customer: Annotated[Customer, Depends(verify_api_key)]):
    with Session(engine) as session:
        #finds ones that haven't been resolved
        return session.exec(select(DeadLetter).where(DeadLetter.replayed_at == None, DeadLetter.customer_id == current_customer.id)).all()

@app.post("/v1/deadletter/{dl_id}/replay")
async def replay_dead_letter(dl_id: UUID, current_customer: Annotated[Customer, Depends(verify_api_key)]):

    with Session(engine) as session:
        deadletter = session.exec(select(DeadLetter).where(DeadLetter.id == dl_id, DeadLetter.customer_id == current_customer.id)).first()
        if deadletter is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"DeadLetter ID: {dl_id} does not exist"
            )
        if deadletter.replayed_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"DeadLetter Event with ID: {dl_id} was already replayed"
            )
        associated_event = session.exec(select(Event).where(Event.id == deadletter.event_id)).first()
        associated_event.status = 'pending'
        associated_event.attempts = 0
        associated_event.next_attempt_at = None
        deadletter.replayed_at = datetime.now()
        session.commit()
        r.lpush("relay:events:pending", str(associated_event.id))
        return f'Retrying event {associated_event.id}'

@app.post("/v1/customers", response_model=CustomerCreated)
async def create_customer( payload: CustomerCreate, _: Annotated[None, Depends(verify_admin_key)], ):
    api_key = secrets.token_urlsafe(32)
    webhook_secret = secrets.token_urlsafe(32)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    customer = Customer(
        name=payload.name,
        api_key_hash=api_key_hash,
        webhook_secret=webhook_secret,
    )
    with Session(engine) as session:
        session.add(customer)
        session.commit()
        session.refresh(customer)
    
    return CustomerCreated(
        id=customer.id,
        name=customer.name,
        api_key=api_key,
        webhook_secret=webhook_secret,
        created_at=customer.created_at,
    )

@app.get("/metrics")
async def get_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)