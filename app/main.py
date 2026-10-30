from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from . import agent, db, paypal

app = FastAPI(title="Mandate")
db.init()


class RunReq(BaseModel):
    goal: str
    naive: bool = False


@app.get("/")
def home():
    return {"app": "Mandate", "status": "running"}


@app.post("/api/run")
def run(req: RunReq):
    return agent.run(req.goal, req.naive)


@app.get("/api/ledger")
def ledger():
    return db.all_rows()


@app.get("/api/mandate")
def mandate():
    m = agent.current_mandate()
    return {"budget_cents": m.budget_cents, "spent_cents": m.spent_cents,
            "max_per_order_cents": m.max_per_order_cents,
            "allowed_categories": m.allowed_categories,
            "allowed_merchants": m.allowed_merchants}


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