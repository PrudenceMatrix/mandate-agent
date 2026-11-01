import json
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import agent, attacks, db, intel, paypal

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Mandate")
db.init()
app.mount("/static", StaticFiles(directory=STATIC), name="static")

_hits = defaultdict(deque)
_lock = threading.Lock()


def _ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    return fwd.split(",")[0].strip()


def _limit(key: str, n: int, window: int = 60):
    now = time.time()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= n:
        raise HTTPException(429, "Too many requests. Wait a minute and try again.")
    q.append(now)


def settle(order_id):
    """Capture a guard-approved order exactly once. Used by the redirect and by the webhook."""
    with _lock:
        row = db.get_by_order(order_id) if order_id else None
        if not row:
            return "unknown_order"
        if row["status"] == "CAPTURED":
            return "paid"
        if row["status"] != "PENDING_APPROVAL":
            return "unknown_order"
        ok, data = paypal.capture_order(order_id)
        done = ok and data.get("status") == "COMPLETED"
        db.set_status(order_id, "CAPTURED" if done else "FAILED")
        return "paid" if done else "failed"


def _mark(order_id, status):
    with _lock:
        row = db.get_by_order(order_id) if order_id else None
        if row and row["status"] != status:
            db.set_status(order_id, status)


class RunReq(BaseModel):
    goal: str = Field(max_length=200)
    naive: bool = False


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/attacks")
def run_attacks(suite: str = "core"):
    if suite not in ("core", "extended"):
        raise HTTPException(400, "suite must be core or extended")
    return attacks.run_lab(suite)


@app.post("/api/reset")
def reset():
    db.reset()
    return {"ok": True}


@app.post("/api/run")
def run(req: RunReq, request: Request):
    _limit(_ip(request), 5)
    _limit("global", 20)
    try:
        return agent.run(req.goal, req.naive)
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {str(e)[:300]}")


@app.get("/api/ledger")
def ledger():
    return db.all_rows()


@app.get("/api/audit/verify")
def audit_verify():
    return db.verify()


@app.post("/api/audit/tamper")
def audit_tamper():
    row_id = db.tamper()
    if row_id is None:
        raise HTTPException(409, "Nothing to tamper with yet. Run the agent first.")
    return {"tampered_row": row_id}


@app.get("/api/intel")
def intel_lookup(domain: str, request: Request):
    _limit("intel:" + _ip(request), 10)
    return intel.lookup(domain[:253])


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
    return RedirectResponse("/?result=" + settle(token))  # only guard-created orders can be captured


@app.get("/paypal/cancel")
def paypal_cancel(token: str = ""):
    if token:
        _mark(token, "CANCELLED")
    return RedirectResponse("/?result=cancelled")


@app.post("/paypal/webhook")
async def paypal_webhook(request: Request):
    if not os.getenv("PAYPAL_WEBHOOK_ID"):
        raise HTTPException(503, "Webhook not configured")
    try:
        event = json.loads(await request.body())
    except ValueError:
        raise HTTPException(400, "Bad JSON")
    if not await run_in_threadpool(paypal.verify_webhook, dict(request.headers), event):
        raise HTTPException(400, "Signature verification failed")
    kind, res = event.get("event_type"), event.get("resource") or {}
    if kind == "CHECKOUT.ORDER.APPROVED":
        await run_in_threadpool(settle, res.get("id"))
    elif kind in ("PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.DENIED"):
        oid = (res.get("supplementary_data") or {}).get("related_ids", {}).get("order_id")
        await run_in_threadpool(_mark, oid, "CAPTURED" if kind.endswith("COMPLETED") else "FAILED")
    return {"ok": True}
