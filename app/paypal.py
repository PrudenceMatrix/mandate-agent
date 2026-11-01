import os
import uuid

import requests
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api-m.sandbox.paypal.com"
APP_URL = os.getenv("BASE_URL", "http://localhost:8000")


def _headers():
    auth = (os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_CLIENT_SECRET"])
    r = requests.post(f"{BASE}/v1/oauth2/token", auth=auth,
                      data={"grant_type": "client_credentials"}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": str(uuid.uuid4())}


def create_order(total_cents: int, description: str):
    body = {"intent": "CAPTURE",
            "purchase_units": [{"description": description[:120],
                                "amount": {"currency_code": "USD",
                                           "value": f"{total_cents / 100:.2f}"}}],
            "payment_source": {"paypal": {"experience_context": {
                "return_url": f"{APP_URL}/paypal/return",
                "cancel_url": f"{APP_URL}/paypal/cancel",
                "user_action": "PAY_NOW"}}}}
    r = requests.post(f"{BASE}/v2/checkout/orders", headers=_headers(), json=body, timeout=30)
    r.raise_for_status()
    o = r.json()
    link = next(l["href"] for l in o["links"] if l["rel"] in ("payer-action", "approve"))
    return o["id"], link


def capture_order(order_id: str):
    r = requests.post(f"{BASE}/v2/checkout/orders/{order_id}/capture",
                      headers=_headers(), json={}, timeout=30)
    try:
        data = r.json()
    except ValueError:
        data = {}
    if not r.ok and any(d.get("issue") == "ORDER_ALREADY_CAPTURED" for d in data.get("details", [])):
        return True, {"status": "COMPLETED"}  # a webhook or a double redirect got there first
    return r.ok, data


def verify_webhook(headers: dict, event: dict) -> bool:
    """Ask PayPal to verify the signature of a webhook delivery (sandbox)."""
    webhook_id = os.getenv("PAYPAL_WEBHOOK_ID")
    body = {"auth_algo": headers.get("paypal-auth-algo"),
            "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "webhook_id": webhook_id, "webhook_event": event}
    if not webhook_id or not all(v for k, v in body.items() if k != "webhook_event"):
        return False
    r = requests.post(f"{BASE}/v1/notifications/verify-webhook-signature",
                      headers=_headers(), json=body, timeout=30)
    return r.ok and r.json().get("verification_status") == "SUCCESS"
