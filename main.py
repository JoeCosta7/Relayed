from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uuid

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

class Event(BaseModel):
    id: str
    destination: str
    event_type: str
    payload: dict
    status: str

events = {}

@app.post("/v1/events")
async def create_event(event: Event):
    event_id = "event: " + uuid.uuid4().hex[:8]
    events[event_id] = {
        "id": event_id,
        "destination_url": event.destination,
        "event_type": event.event_type,
        "payload": event.payload,
        "status": "pending"
    }
    return JSONResponse(status_code=202, content={"id": event_id, "status": "queued"})

@app.get("/v1/events")
async def list_events():
    return list(events.values())


