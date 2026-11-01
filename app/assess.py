from . import classifier, intel
from .catalog import MERCHANTS, PRODUCTS
from .guard import evaluate


def assess(mandate, proposal):
    """Deterministic guard first, with live merchant data when enabled, then an optional AI second opinion."""
    merchants = dict(MERCHANTS)
    p = PRODUCTS.get(proposal.product_id)
    if p:
        merchants[p.merchant_id] = intel.refresh_merchant(MERCHANTS[p.merchant_id])
    d = evaluate(mandate, proposal, None, merchants)
    if p and d.verdict != "BLOCK":
        op = classifier.second_opinion(f"{p.title}\n{p.description}")
        if op and op["injection"]:
            d.verdict = "BLOCK"
            d.reasons.append("AI classifier flagged possible injection: " + op["reason"][:120])
    return d
