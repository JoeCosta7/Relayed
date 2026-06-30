from sqlmodel import Field, SQLModel, create_engine, Session, select
import os
from sqlalchemy import Column, DateTime, String
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from uuid import UUID, uuid4
from dotenv import load_dotenv
from pathlib import Path
import redis
import secrets
from enum import Enum

load_dotenv(Path(__file__).parent / ".env", override=False)

DATABASE_URL = os.getenv("DATABASE_URL")

class SubscriptionStatusEnum(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"

class DeliveryStatusEnum(str, Enum):
    PENDING = "pending"
    RETRYING = "retrying"
    DELIVERED = "delivered"
    DEAD_LETTERED = "dead_lettered"

class DeadLetter(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    event_id: UUID = Field(foreign_key="event.id", index=True)
    attempts : int = Field(default=0)
    status_code : Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    failed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc),sa_column=Column(DateTime(timezone=True), nullable=False))
    replayed_at: Optional[datetime] = Field(default=None,sa_column=Column(DateTime(timezone=True), nullable=True))
    customer_id : UUID = Field(foreign_key="customer.id", index=True)
    subscription_id : UUID = Field(foreign_key="subscription.id", index=True)
    delivery_id : UUID = Field(foreign_key="delivery.id", index=True)

class EventBase(SQLModel):
    event_type: str
    payload: Dict[str, Any] = Field(default_factory=dict, sa_type=JSONB)

class Event(EventBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    customer_id : UUID = Field(foreign_key="customer.id", index=True)

class Customer(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    api_key_hash: str = Field(index=True, unique=True)
    webhook_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))

    # Request: what the admin sends
class CustomerCreate(SQLModel):
    name: str

# Response: what the admin gets back, ONCE
class CustomerCreated(SQLModel):
    id: UUID
    name: str
    api_key: str          # plaintext, shown only here
    webhook_secret: str   # plaintext, shown only here
    created_at: datetime

#For Request
class SubscriptionCreate(SQLModel):
    destination_url: str
    event_types : list[str]
    description : Optional[str] = None

#For GET
class SubscriptionRead(SQLModel):
    id : UUID 
    customer_id : UUID 
    destination_url: str
    event_types : list[str] 
    description : Optional[str] = None
    status : SubscriptionStatusEnum 
    created_at: datetime 

#For POST
class SubscriptionCreated(SQLModel):
    id : UUID
    customer_id : UUID 
    destination_url: str
    event_types : list[str]
    description : Optional[str] = None
    webhook_secret: str 
    status : SubscriptionStatusEnum 
    created_at: datetime


class Subscription(SQLModel, table=True):
    id : UUID = Field(default_factory=uuid4, primary_key=True)
    customer_id : UUID = Field(foreign_key="customer.id", index=True)
    destination_url: str
    event_types : list[str] = Field(sa_column=Column(ARRAY(String), nullable=False))
    description : Optional[str] = None
    webhook_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    status : SubscriptionStatusEnum = Field(default=SubscriptionStatusEnum.ACTIVE)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc),sa_column=Column(DateTime(timezone=True), nullable=False))

class Delivery(SQLModel, table=True):
    id : UUID = Field(default_factory=uuid4, primary_key=True)
    event_id : UUID = Field(foreign_key="event.id", index=True)
    customer_id : UUID = Field(foreign_key="customer.id", index=True)
    subscription_id : UUID = Field(foreign_key="subscription.id", index=True)
    status : DeliveryStatusEnum = Field(default=DeliveryStatusEnum.PENDING)
    attempts : int = Field(default=0) 
    next_attempt_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    status_code : Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))


engine = create_engine(DATABASE_URL, echo=True)
r = redis.Redis(host='redis', port=6379, decode_responses=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)



