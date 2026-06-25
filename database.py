from sqlmodel import Field, SQLModel, create_engine, Session, select
import os
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB
from uuid import UUID, uuid4
from dotenv import load_dotenv
from pathlib import Path
import redis

load_dotenv(Path(__file__).parent / ".env", override=False)

DATABASE_URL = os.getenv("DATABASE_URL")

class DeadLetter(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    event_id: UUID = Field(foreign_key="event.id")
    attempts : int
    status_code : Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    failed_at : datetime = Field(default_factory=datetime.now)
    replayed_at: Optional[datetime] = None
    customer_id : UUID = Field(foreign_key="customer.id", index=True)

class EventBase(SQLModel):
    destination_url: str
    event_type: str
    payload: Dict[str, Any] = Field(default=None, sa_type=JSONB)

class Event(EventBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    status: str = "pending"
    created_at: datetime = Field(default_factory=datetime.now)
    attempts: int = Field(default = 0)
    next_attempt_at: Optional[datetime] = Field(default=None)
    customer_id : UUID = Field(foreign_key="customer.id", index=True)

class Customer(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    api_key_hash: str = Field(index=True, unique=True)
    webhook_secret : str
    created_at: datetime = Field(default_factory=datetime.now)

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


engine = create_engine(DATABASE_URL, echo=True)
r = redis.Redis(host='redis', port=6379, decode_responses=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)



