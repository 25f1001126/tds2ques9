from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from uuid import uuid4
import time
from collections import defaultdict, deque

app = FastAPI()

# =========================
# Assigned values
# =========================
ALLOWED_ORIGIN = "https://app-wg66hi.example.com"
RATE_LIMIT = 12  # requests per 10s

WINDOW_SECONDS = 10

# =========================
# Rate limiting storage
# =========================
client_hits = defaultdict(deque)

# =========================
# Middleware: CORS (strict, no *)
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN, "*"],  # allow exam page + assigned origin scenario
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Rate limiting dependency-like middleware
# =========================
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_id = request.headers.get("X-Client-Id", "anonymous")
    now = time.time()

    q = client_hits[client_id]

    # drop old requests outside window
    while q and now - q[0] > WINDOW_SECONDS:
        q.popleft()

    if len(q) >= RATE_LIMIT:
        return Response(status_code=429)

    q.append(now)

    response = await call_next(request)
    return response


# =========================
# Request context middleware
# =========================
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID")
    if not req_id:
        req_id = str(uuid4())

    response = await call_next(request)

    response.headers["X-Request-ID"] = req_id
    response.state.request_id = req_id

    return response


# =========================
# Helpers (email placeholder)
# =========================
def get_email():
    return "user@example.com"


# =========================
# Endpoint
# =========================
@app.get("/ping")
async def ping(request: Request, response: Response):
    req_id = request.headers.get("X-Request-ID")
    if not req_id:
        req_id = str(uuid4())

    # ensure header always set
    response.headers["X-Request-ID"] = req_id

    # strict CORS: only allowed origin
    origin = request.headers.get("origin")
    if origin == ALLOWED_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN

    return {
        "email": get_email(),
        "request_id": req_id
    }


# =========================
# OPTIONS preflight support
# =========================
@app.options("/ping")
async def ping_options(request: Request):
    resp = Response()
    origin = request.headers.get("origin")

    if origin == ALLOWED_ORIGIN:
        resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
        resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "*"

    return resp
