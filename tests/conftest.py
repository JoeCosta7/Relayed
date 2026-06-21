import pytest
from sqlmodel import Session
from sqlalchemy import text
from database import engine

@pytest.fixture(autouse=True)
def clean_db():
    # Run before each test
    with Session(engine) as session:
        session.execute(text("TRUNCATE TABLE deadletter, event RESTART IDENTITY CASCADE"))
        session.commit()
    yield