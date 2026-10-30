import os, uuid, requests
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api-m.sandbox.paypal.com"
AUTH = (os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_CLIENT_SECRET"])
APP_URL = os.getenv("BASE_URL", "http://localhost:8000")


def _headers():
    r = requests.post(f"{BASE}/v1/oauth2/token", auth=AUTH,
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
    return r.ok, r.json()