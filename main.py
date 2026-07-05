import time
import uuid
from collections import defaultdict, deque
from typing import Optional

from fastapi import FastAPI, Request, Header, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- CONFIG ----------------
TOTAL_ORDERS = 59
RATE_LIMIT = 16
WINDOW = 10  # seconds

# ---------------- STORAGE ----------------
idempotency_store = {}
rate_store = defaultdict(deque)


# ---------------- RATE LIMIT MIDDLEWARE ----------------
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    client_id = request.headers.get("X-Client-Id") or request.headers.get("x-client-id")

    if client_id:
        now = time.time()
        q = rate_store[client_id]

        # drop timestamps outside the window
        while q and now - q[0] > WINDOW:
            q.popleft()

        if len(q) >= RATE_LIMIT:
            oldest = q[0]
            retry_after = max(1, int(WINDOW - (now - oldest)) + 1)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )

        q.append(now)

    response = await call_next(request)
    return response


# ---------------- 1. IDEMPOTENT ORDER CREATION ----------------
@app.post("/orders")
async def create_order(
    response: Response,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Missing Idempotency-Key header")

    if idempotency_key in idempotency_store:
        response.status_code = 200
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4()),
        "status": "created",
        "ts": time.time(),
    }
    idempotency_store[idempotency_key] = order
    response.status_code = 201
    return order


# ---------------- 2. CURSOR PAGINATION ----------------
# Query params taken as raw strings and parsed manually so malformed/unexpected
# values (empty string, "None", floats, etc.) never produce a 422 — they just
# fall back to safe defaults.
@app.get("/orders")
def list_orders(request: Request):
    raw_limit = request.query_params.get("limit")
    raw_cursor = request.query_params.get("cursor")

    try:
        limit = int(raw_limit) if raw_limit not in (None, "") else 10
    except (TypeError, ValueError):
        limit = 10
    if limit < 1:
        limit = 1

    try:
        start = int(raw_cursor) if raw_cursor not in (None, "", "None", "null") else 1
    except (TypeError, ValueError):
        start = 1
    if start < 1:
        start = 1

    end = min(start + limit, TOTAL_ORDERS + 1)
    if start > TOTAL_ORDERS:
        items = []
        next_cursor = None
    else:
        items = [{"id": i} for i in range(start, end)]
        next_cursor = str(end) if end <= TOTAL_ORDERS else None

    return {
        "items": items,
        "next_cursor": next_cursor,
        "next": next_cursor,   # alias
        "orders": items,       # alias
    }


# ---------------- HEALTH CHECK ----------------
@app.get("/health")
def health():
    return {"status": "ok"}
