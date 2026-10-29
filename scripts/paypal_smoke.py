import os, sys, uuid, requests
from dotenv import load_dotenv

load_dotenv()
BASE = "https://api-m.sandbox.paypal.com"
AUTH = (os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_CLIENT_SECRET"])

def token():
    r = requests.post(f"{BASE}/v1/oauth2/token", auth=AUTH,
                      data={"grant_type": "client_credentials"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]

def headers():
    return {"Authorization": f"Bearer {token()}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": str(uuid.uuid4())}

def create(amount="25.00"):
    body = {"intent": "CAPTURE",
            "purchase_units": [{"amount": {"currency_code": "USD", "value": amount}}],
            "payment_source": {"paypal": {"experience_context": {
                "return_url": "https://example.com/return",
                "cancel_url": "https://example.com/cancel",
                "user_action": "PAY_NOW"}}}}
    r = requests.post(f"{BASE}/v2/checkout/orders", headers=headers(), json=body, timeout=30)
    r.raise_for_status()
    o = r.json()
    link = next(l["href"] for l in o["links"] if l["rel"] in ("payer-action", "approve"))
    print("ORDER ID:", o["id"], "| STATUS:", o["status"])
    print("APPROVE HERE:", link)

def capture(order_id):
    r = requests.post(f"{BASE}/v2/checkout/orders/{order_id}/capture",
                      headers=headers(), json={}, timeout=30)
    print(r.status_code, r.json().get("status"), r.json().get("id"))
    if not r.ok:
        print(r.text)

if __name__ == "__main__":
    cmd = sys.argv[1]
    create() if cmd == "create" else capture(sys.argv[2])