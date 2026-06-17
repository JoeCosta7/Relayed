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
    
engine = create_engine(DATABASE_URL, echo=True)
r = redis.Redis(host='localhost', port=6379, decode_responses=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)



