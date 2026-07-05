from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import time
import uuid
from collections import defaultdict, deque

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

T = 59
R = 16

catalog = [{"id": i, "name": f"Order {i}"} for i in range(1, T + 1)]

idempotency_store = {}
orders_created = []

client_hits = defaultdict(deque)


class OrderIn(BaseModel):
    item: Optional[str] = None
    quantity: Optional[int] = 1


@app.post("/orders")
async def create_order(request: Request, payload: OrderIn, idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key")):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header required")

    if idempotency_key in idempotency_store:
        saved = idempotency_store[idempotency_key]
        return JSONResponse(status_code=201, content=saved)

    order_id = str(uuid.uuid4())
    order = {
        "id": order_id,
        "item": payload.item,
        "quantity": payload.quantity,
    }
    idempotency_store[idempotency_key] = order
    orders_created.append(order)
    return JSONResponse(status_code=201, content=order)


@app.get("/orders")
async def list_orders(limit: int = 10, cursor: Optional[str] = None):
    if limit < 1:
        limit = 1

    start_index = 0
    if cursor:
        try:
            start_index = int(cursor)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid cursor")

    items = catalog[start_index:start_index + limit]
    next_cursor = None

    if start_index + limit < len(catalog):
        next_cursor = str(start_index + limit)

    return {
        "items": items,
        "next_cursor": next_cursor
    }


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_id = request.headers.get("X-Client-Id")

    if client_id:
        now = time.time()
        window_start = now - 10
        hits = client_hits[client_id]

        while hits and hits[0] < window_start:
            hits.popleft()

        if len(hits) >= R:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": "10"}
            )

        hits.append(now)

    response = await call_next(request)
    return response
