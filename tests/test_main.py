from fastapi.testclient import TestClient

from app import agent, db, main, paypal

client = TestClient(main.app)
EVENT = {"event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": "O1"}}


def pending(order_id="O1"):
    db.add(goal="g", product_id="p", product="P", quantity=1, claimed_cents=2499, total_cents=2499,
           merchant_id="deskcraft", verdict="ALLOW", reasons="[]", order_id=order_id,
           status="PENDING_APPROVAL")


def capture_ok(calls):
    return lambda oid: (calls.append(oid) or True, {"status": "COMPLETED"})


def test_return_captures_exactly_once(monkeypatch):
    calls = []
    monkeypatch.setattr(paypal, "capture_order", capture_ok(calls))
    pending()
    r = client.get("/paypal/return?token=O1", follow_redirects=False)
    assert r.headers["location"] == "/?result=paid"
    client.get("/paypal/return?token=O1", follow_redirects=False)
    assert calls == ["O1"] and db.spent_cents() == 2499 and db.verify()["ok"]


def test_return_refuses_orders_the_guard_never_made(monkeypatch):
    calls = []
    monkeypatch.setattr(paypal, "capture_order", capture_ok(calls))
    r = client.get("/paypal/return?token=NOPE", follow_redirects=False)
    assert r.headers["location"] == "/?result=unknown_order" and calls == []


def test_webhook_not_configured(monkeypatch):
    monkeypatch.delenv("PAYPAL_WEBHOOK_ID", raising=False)
    assert client.post("/paypal/webhook", json=EVENT).status_code == 503


def test_webhook_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "W1")
    monkeypatch.setattr(paypal, "verify_webhook", lambda h, e: False)
    pending()
    assert client.post("/paypal/webhook", json=EVENT).status_code == 400
    assert db.get_by_order("O1")["status"] == "PENDING_APPROVAL"


def test_webhook_approved_event_captures(monkeypatch):
    calls = []
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "W1")
    monkeypatch.setattr(paypal, "verify_webhook", lambda h, e: True)
    monkeypatch.setattr(paypal, "capture_order", capture_ok(calls))
    pending()
    assert client.post("/paypal/webhook", json=EVENT).status_code == 200
    assert db.get_by_order("O1")["status"] == "CAPTURED" and calls == ["O1"]


def test_webhook_capture_completed_marks_paid(monkeypatch):
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "W1")
    monkeypatch.setattr(paypal, "verify_webhook", lambda h, e: True)
    pending()
    ev = {"event_type": "PAYMENT.CAPTURE.COMPLETED",
          "resource": {"supplementary_data": {"related_ids": {"order_id": "O1"}}}}
    assert client.post("/paypal/webhook", json=ev).status_code == 200
    assert db.get_by_order("O1")["status"] == "CAPTURED" and db.verify()["ok"]


def test_attack_endpoints():
    assert client.get("/api/attacks").json()["all_passed"]
    assert client.get("/api/attacks?suite=extended").json()["all_passed"]
    assert client.get("/api/attacks?suite=nope").status_code == 400


def test_audit_endpoints():
    assert client.post("/api/audit/tamper").status_code == 409
    pending()
    assert client.get("/api/audit/verify").json()["ok"]
    client.post("/api/audit/tamper")
    assert not client.get("/api/audit/verify").json()["ok"]
    client.post("/api/reset")
    assert client.get("/api/audit/verify").json()["ok"]


def test_intel_endpoint(monkeypatch):
    monkeypatch.setattr(main.intel, "lookup", lambda d: {"domain": d, "verdict": "ALLOW", "reasons": []})
    assert client.get("/api/intel?domain=shop.com").json()["verdict"] == "ALLOW"


def test_demo_flow_two_blocks_then_an_order(monkeypatch):
    monkeypatch.setattr(agent.paypal, "create_order", lambda cents, desc: ("ORD1", "https://x/approve"))
    r = agent._run_fallback("Buy me the cheapest laptop stand")
    verdicts = [t["result"]["verdict"] for t in r["trace"] if t["tool"] == "propose_purchase"]
    assert verdicts == ["BLOCK", "BLOCK", "ALLOW"] and r["order"]["order_id"] == "ORD1"
    assert db.verify()["ok"]
