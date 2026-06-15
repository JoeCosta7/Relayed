from sqlmodel import Field, SQLModel, create_engine, Session, select
import os
from contextlib import asynccontextmanager
from typing import Dict, Any
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.dialects.postgresql import JSONB
from uuid import UUID, uuid4
from dotenv import load_dotenv
from pathlib import Path
import random
import asyncio

fail_mode = False

def startup():
    print("Toy destination running on port 9000")

app = FastAPI()

@app.post("/hook")
async def receive_hook(payload: Dict[str, Any]):
    await asyncio.sleep(2)
    if random.random() < 0.25:
        return JSONResponse(status_code=500, content={"message": "Simulated failure"})
    print("Received payload:", payload)
    if fail_mode:
        return JSONResponse(status_code=500, content={"message": "Simulated failure"})
    return JSONResponse(status_code=200, content={"message": "Payload received successfully"})

@app.post("/fail/on")
async def turn_on_fail_mode():
    global fail_mode
    fail_mode = True

@app.post("/fail/off")
async def turn_off_fail_mode():
    global fail_mode
    fail_mode = False

