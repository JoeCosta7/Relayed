from dotenv import load_dotenv
import os
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env.test", override=True)

import pytest
from sqlmodel import Session, SQLModel
from sqlalchemy import text
from database import engine

@pytest.fixture(scope="session", autouse=True)
def setup_schema():
    SQLModel.metadata.create_all(engine)
    yield

@pytest.fixture(autouse=True)
def clean_tables():
    with Session(engine) as session:
        session.exec(text("TRUNCATE TABLE deadletter, event RESTART IDENTITY CASCADE"))
        session.commit()