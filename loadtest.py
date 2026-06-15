import asyncio
import json
import httpx
from database import Event, EventBase
import random 
import numpy as np
import time

async def call_api(payload : json, x: int, client: httpx.AsyncClient, sem: asyncio.Semaphore):
    try:
        async with sem:
            start = time.perf_counter()
            result = await client.post('http://127.0.0.1:8000/v1/events', json=payload)
            print(f'Calling API {x}')
            duration = time.perf_counter() - start
            return duration
    except Exception as e:
        print(f"There was an error: {type(e).__name__}: {e}")
        return None

async def main():
    print("Starting load test....")
    payload = {
    "destination_url": "http://127.0.0.1:9000/hook",
    "event_type": "order.paid",
    "payload": {"order_id": 123}
    }
    sem = asyncio.Semaphore(100)
    elapsed_start = time.perf_counter()
    async with httpx.AsyncClient() as client:
        gathered_results = await asyncio.gather(
            *[call_api(payload, x, client, sem) for x in range(1, 2000)]         
        )
    durations = [r for r in gathered_results if r is not None]
    data = np.array(durations)
    p50, p95, p99 = np.percentile(data, [50, 95, 99])
    print(f"50th Percentile: {p50}")
    print(f"95th Percentile: {p95}")
    print(f"99th Percentile: {p99}")
    elapsed_total = time.perf_counter() - elapsed_start
    requests_per_second = len(durations) / elapsed_total

    print(elapsed_total, requests_per_second)

asyncio.run(main())
