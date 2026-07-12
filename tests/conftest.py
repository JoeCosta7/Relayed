from dotenv import load_dotenv
import os
from pathlib import Path

if not os.getenv("CI"):
    load_dotenv(Path(__file__).parent / ".env.test", override=True)

import pytest
from sqlmodel import Session, SQLModel
from sqlalchemy import text
from database import engine
from database import Customer, Subscription, TierEnum
import secrets
import hashlib

@pytest.fixture(scope="session", autouse=True)
def setup_schema():
    # Drop first so schema changes (e.g. new columns) are always reflected;
    # create_all alone won't alter an already-existing table.
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield

@pytest.fixture(autouse=True)
def clean_tables():
    with Session(engine) as session:
        session.exec(text("TRUNCATE TABLE deadletter, event, customer RESTART IDENTITY CASCADE"))
        session.commit()

@pytest.fixture(scope="function")
def create_test_customer(clean_tables):
    """Factory fixture: call create_test_customer() to make a tenant, once per customer needed."""
    def _create(name: str | None = None, tier: TierEnum = TierEnum.FREE) -> dict:
        if name is None:
            name = f"test-customer-{secrets.token_hex(4)}"
        api_key = secrets.token_urlsafe(32)
        api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        webhook_secret = secrets.token_urlsafe(32)
        customer = Customer(
            name=name,
            api_key_hash=api_key_hash,
            webhook_secret=webhook_secret,
            tier=tier,
        )
        with Session(engine) as session:
            session.add(customer)
            session.commit()
            session.refresh(customer)
        return {"customer": customer, "api_key": api_key}
    return _create

@pytest.fixture(scope="function")
def test_customer(create_test_customer):
    return create_test_customer()

@pytest.fixture(scope="function")
def test_subscription(test_customer):
    customer_id = test_customer["customer"].id
    destination_url = "https://example.com/webhook"
    event_types = ["test"]
    subscription = Subscription(
        customer_id = customer_id,
        destination_url = destination_url,
        event_types = event_types
    )
    with Session(engine) as session: 
        session.add(subscription)
        session.commit() 
        session.refresh(subscription)
    return subscription