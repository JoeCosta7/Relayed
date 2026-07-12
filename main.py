from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status, Header, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, Response
from typing import Annotated
from redis_client import r
from rate_limit import check_rate_limit
import secrets
from database import (Event, EventBase, DeadLetter, Customer, CustomerCreated, CustomerCreate, Subscription,  SubscriptionCreate, 
SubscriptionCreated, SubscriptionRead, Delivery, DeliveryStatusEnum, SubscriptionStatusEnum, KeyRotated, KeyRotateRequest, engine, create_db_and_tables)
from sqlmodel import Session, select, or_
from sqlalchemy import or_
from app_metrics import EVENTS
import os
from uuid import UUID
from datetime import datetime, timezone, timedelta
import hashlib
import logging

from prometheus_client import generate_latest,CONTENT_TYPE_LATEST


@asynccontextmanager
async def lifespan(app: FastAPI):
    #build db on start
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)
logger = logging.getLogger(__name__)
security = HTTPBearer()

@app.get("/")
async def root():
    return {"message": "Hello World"}

async def verify_api_key(credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)]):
    with Session(engine) as session:
        incoming_hash = hashlib.sha256(credentials.credentials.encode("utf8")).hexdigest()
        customer = session.exec(
            select(Customer).where(
                or_(Customer.api_key_hash == incoming_hash, Customer.previous_api_key_hash == incoming_hash)
            )
        ).first()
    if customer is None:
        raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect API KEY",
                headers={"WWW-Authenticate": "Bearer"},
            )
    if customer.api_key_hash == incoming_hash:
        pass
    elif customer.previous_api_key_expires_at is None or customer.previous_api_key_expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect API KEY",
                headers={"WWW-Authenticate": "Bearer"},
            )
    is_allowed, retry_after = check_rate_limit(customer)
    if not is_allowed:
        raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
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

@app.post("/v1/keys/rotate", response_model=KeyRotated, status_code=200)
async def rotate_keys(current_customer: Annotated[Customer, Depends(verify_api_key)], request: KeyRotateRequest = KeyRotateRequest()):
    new_api_key = secrets.token_urlsafe(32)
    new_api_key_hash = hashlib.sha256(new_api_key.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=request.grace_period_seconds)
    with Session(engine) as session:
        customer = session.get(Customer, current_customer.id)
        customer.previous_api_key_hash = customer.api_key_hash
        customer.api_key_hash = new_api_key_hash
        customer.previous_api_key_expires_at = expires_at
        session.commit()
    return {"api_key": new_api_key, "grace_period_expires_at": expires_at}


@app.post("/v1/events")
async def create_event(event: EventBase, current_customer: Annotated[Customer, Depends(verify_api_key)], idempotency_key: Annotated[str, Header()]):
    #idempotency check, make sure not used beofre
    idempotency_redis_key = f'idempotency:{current_customer.id}:{idempotency_key}'
    claimed = r.set(idempotency_redis_key, "claimed", ex=86400, nx=True)
    #cache hit, already exists
    if not claimed:
        cached_event_id = UUID(r.get(idempotency_redis_key))
        with Session(engine) as session:
            deliveries = session.exec(select(Delivery).where(Delivery.event_id == cached_event_id, Delivery.customer_id == current_customer.id,)).all()
            return JSONResponse(status_code=202, content={"event_id": str(cached_event_id), "delivery_ids": [str(d.id) for d in deliveries]}, headers={"Idempotent-Replayed": "true"})
    with Session(engine) as session:
        newEvent = Event(
            event_type=event.event_type,
            payload=event.payload,
            customer_id = current_customer.id
        )
        session.add(newEvent) 
        session.flush()
        #find all subscriptions an event has
        matching_subscriptions = session.exec(select(Subscription).where(Subscription.customer_id == current_customer.id, Subscription.status == "active", Subscription.event_types.contains([event.event_type]))).all()
        #deliver for every subscription
        new_deliveries = []
        for subscription in matching_subscriptions:
            new_deliveries.append(Delivery(
                event_id=newEvent.id,
                subscription_id=subscription.id,
                customer_id=current_customer.id,
            ))
        session.add_all(new_deliveries)
        session.commit()
        EVENTS.inc()
        logger.info("event created", extra={"event_id": str(newEvent.id),"customer_id": str(current_customer.id), "event_type": event.event_type, "delivery_count": len(new_deliveries)})
        delivery_ids = [str(d.id) for d in new_deliveries]
        r.set(idempotency_redis_key, str(newEvent.id), ex=86400)
        for d in new_deliveries:
            r.lpush("relay:deliveries:pending", str(d.id))
        return JSONResponse(status_code=202,content={"event_id": str(newEvent.id), "delivery_ids": delivery_ids})

@app.get("/v1/events")
async def list_events(current_customer: Annotated[Customer, Depends(verify_api_key)]):
    with Session(engine) as session:
        return session.exec(select(Event).where(Event.customer_id == current_customer.id)).all()

@app.get("/v1/deadletter")
async def list_dead_letter_events(current_customer: Annotated[Customer, Depends(verify_api_key)]):
    with Session(engine) as session:
        #finds ones that haven't been resolved
        return session.exec(select(DeadLetter).where(DeadLetter.replayed_at == None, DeadLetter.customer_id == current_customer.id)).all()

@app.post("/v1/deadletter/{dl_id}/replay", status_code=202)
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
        subscription = session.exec(select(Subscription).where(Subscription.id == deadletter.subscription_id)).first()
        if deadletter.subscription_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subscription ID: {subscription.id} does not exist"
            )
        if subscription.status == SubscriptionStatusEnum.DISABLED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Subscription no longer active"
            )
        new_delivery = Delivery(
            event_id=deadletter.event_id,
            subscription_id=deadletter.subscription_id,
            customer_id=deadletter.customer_id,
            status = DeliveryStatusEnum.PENDING, 
            attempts = 0,
        )
        session.add(new_delivery) 
        deadletter.replayed_at = datetime.now(timezone.utc)
        session.commit()
        r.lpush("relay:deliveries:pending", str(new_delivery.id))
        return {"delivery_ids": [new_delivery.id]}


@app.post("/v1/customers", response_model=CustomerCreated)
async def create_customer( payload: CustomerCreate, _: Annotated[None, Depends(verify_admin_key)], ):
    customer_api_key = secrets.token_urlsafe(32)
    customer_webhook_secret = secrets.token_urlsafe(32)
    customer_api_key_hash = hashlib.sha256(customer_api_key.encode()).hexdigest()
    customer = Customer(name=payload.name,api_key_hash=customer_api_key_hash,webhook_secret=customer_webhook_secret,)
    with Session(engine) as session:
        session.add(customer)
        session.commit()
        session.refresh(customer)
    return CustomerCreated(id=customer.id,name=customer.name,api_key=customer_api_key,webhook_secret=customer_webhook_secret,created_at=customer.created_at)

    

@app.post("/v1/subscriptions", response_model=SubscriptionCreated, status_code=201)
async def create_subscription(payload: SubscriptionCreate, current_customer: Annotated[Customer, Depends(verify_api_key)]):
    subscription = Subscription(destination_url=payload.destination_url, event_types=payload.event_types, description=payload.description, customer_id = current_customer.id)
    with Session(engine) as session:
        session.add(subscription)
        session.commit()
        session.refresh(subscription)
    return subscription

@app.get("/v1/subscriptions", response_model=list[SubscriptionRead])
async def get_subscriptions(current_customer: Annotated[Customer, Depends(verify_api_key)],):
    with Session(engine) as session:
        return session.exec(select(Subscription).where(Subscription.customer_id == current_customer.id, Subscription.status != SubscriptionStatusEnum.DISABLED)).all()
    
@app.get("/v1/subscriptions/{subscription_id}", response_model=SubscriptionRead)
async def get_specific_subscription(subscription_id: UUID, current_customer: Annotated[Customer, Depends(verify_api_key)]):
    with Session(engine) as session:
        subscription = session.exec(select(Subscription).where(Subscription.customer_id == current_customer.id, Subscription.id == subscription_id)).first()
        if not subscription or subscription.status == SubscriptionStatusEnum.DISABLED:
            raise HTTPException(status_code=404, detail="not found")
        return subscription

@app.delete("/v1/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: UUID, current_customer: Annotated[Customer, Depends(verify_api_key)]):
    with Session(engine) as session:
        subscription_to_delete = session.exec(select(Subscription).where(Subscription.customer_id == current_customer.id, Subscription.id == subscription_id)).first()
        if not subscription_to_delete or subscription_to_delete.status == SubscriptionStatusEnum.DISABLED:
            raise HTTPException(status_code=404, detail="not found")
        subscription_to_delete.status = SubscriptionStatusEnum.DISABLED
        session.commit()
        return Response(status_code=204)

@app.get("/v1/events")
async def list_events(current_customer: Annotated[None, Depends(verify_api_key)]):
    with Session(engine) as session:
        return session.exec(select(Event).where(Event.customer_id == current_customer.id)).all()

@app.get("/metrics")
async def get_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)