from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uuid

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

events = {}

@app.post("/v1/events")
async def create_event(request: Request):
    body = await request.json()
    event_id = "evt_" + uuid.uuid4().hex[:8]
    events[event_id] = {
        "id": event_id,
        "destination_url": body.get("destination"),
        "event_type": body.get("event"),
        "payload": body.get("data"),
        "status": "pending",
    }
    # The whole point: respond instantly, do no slow work here.
    return JSONResponse(status_code=202, content={"id": event_id, "status": "queued"})

@app.get("/v1/events")
async def list_events():
    return list(events.values())

# class Event(BaseModel):
#     id: str
#     destination: str
#     event_type: str
#     payload: dict
#     status: str

# @app.post("/v1/events")
# async def create_event(request: Request):
#     body = await request.json()
#     event_id = "event " + uuid.uuid4().hex[:8]
#     event = Event(
#         id=event_id,
#         destination=body.get("destination"),
#         event_type=body.get("event"),
#         payload=body.get("data"),
#         status="pending"
#     )
#     return event

# events = {}

# @app.get("/v1/events")
# async def list_events():
#     return list(events.values())