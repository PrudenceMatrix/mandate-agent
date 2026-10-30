import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import agent, attacks, db, paypal

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Mandate")
db.init()

_hits = defaultdict(deque)


def _limit(key: str, n: int, window: int = 60):
    now = time.time()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= n:
        raise HTTPException(429, "Too many runs. Wait a minute and try again.")
    q.append(now)


class RunReq(BaseModel):
    goal: str = Field(max_length=200)
    naive: bool = False


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/attacks")
def run_attacks():
    return attacks.run_lab()


@app.post("/api/reset")
def reset():
    db.reset()
    return {"ok": True}


@app.post("/api/run")
def run(req: RunReq, request: Request):
    ip = request.headers.get("x-forwarded-for",
                             request.client.host if request.client else "unknown")
    _limit(ip.split(",")[0].strip(), 5)
    _limit("global", 20)
    try:
        return agent.run(req.goal, req.naive)
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {str(e)[:300]}")


@app.get("/api/ledger")
def ledger():
    return db.all_rows()


@app.get("/api/mandate")
def mandate():
    m = agent.current_mandate()
    return {"budget_cents": m.budget_cents,
            "spent_cents": m.spent_cents,
            "max_per_order_cents": m.max_per_order_cents,
            "allowed_categories": m.allowed_categories,
            "allowed_merchants": m.allowed_merchants,
            "environment": "sandbox" if "sandbox" in paypal.BASE else "LIVE"}


@app.get("/paypal/return")
def paypal_return(token: str):
    row = db.get_by_order(token)  # only orders the guard created can ever be captured
    if not row or row["status"] != "PENDING_APPROVAL":
        return RedirectResponse("/?result=unknown_order")
    ok, data = paypal.capture_order(token)
    done = ok and data.get("status") == "COMPLETED"
    db.set_status(token, "CAPTURED" if done else "FAILED")
    return RedirectResponse("/?result=" + ("paid" if done else "failed"))


@app.get("/paypal/cancel")
def paypal_cancel(token: str = ""):
    if token:
        db.set_status(token, "CANCELLED")
    return RedirectResponse("/?result=cancelled")