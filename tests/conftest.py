from dotenv import load_dotenv
import os
from pathlib import Path

if not os.getenv("CI"):
    load_dotenv(Path(__file__).parent / ".env.test", override=True)

import pytest
from sqlmodel import Session, SQLModel
from sqlalchemy import text
from database import engine
from database import Customer
import secrets
import hashlib

@pytest.fixture(scope="session", autouse=True)
def setup_schema():
    SQLModel.metadata.create_all(engine)
    yield

@pytest.fixture(autouse=True)
def clean_tables():
    with Session(engine) as session:
        session.exec(text("TRUNCATE TABLE deadletter, event, customer RESTART IDENTITY CASCADE"))
        session.commit()

@pytest.fixture(scope="function")
def test_customer(clean_tables):
    api_key = secrets.token_urlsafe(32)
    api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    webhook_secret = secrets.token_urlsafe(32)
    customer = Customer(
        name="test-customer",
        api_key_hash=api_key_hash,
        webhook_secret=webhook_secret,
    )
    with Session(engine) as session: 
        session.add(customer)
        session.commit() 
        session.refresh(customer)
    return {"customer": customer, "api_key": api_key}