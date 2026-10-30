from dataclasses import replace

from app.catalog import PRODUCTS
from app.guard import evaluate
from app.models import Mandate, Proposal

M = Mandate(budget_cents=10000, max_per_order_cents=5000,
            allowed_categories=("office",),
            allowed_merchants=("deskcraft", "gadgetbarn"))


def prop(pid, qty=1, claimed=None):
    total = PRODUCTS[pid].price_cents * qty
    return Proposal(pid, qty, total if claimed is None else claimed)


def has(decision, word):
    return any(word in r.lower() for r in decision.reasons)


def test_clean_purchase_allowed():
    assert evaluate(M, prop("p_stand_1")).verdict == "ALLOW"

def test_over_per_order_cap_blocked():
    d = evaluate(M, prop("p_laptop"))
    assert d.verdict == "BLOCK" and has(d, "per-order cap")

def test_budget_exhausted_blocked():
    d = evaluate(replace(M, spent_cents=9000), prop("p_hub"))
    assert d.verdict == "BLOCK" and has(d, "remaining budget")

def test_disallowed_new_merchant_blocked():
    d = evaluate(M, prop("p_stand_cheap"))
    assert d.verdict == "BLOCK" and has(d, "allowlist") and has(d, "days old")

def test_prompt_injection_blocked():
    d = evaluate(M, prop("p_stand_poison"))
    assert d.verdict == "BLOCK" and has(d, "injection")

def test_amount_tampering_blocked():
    d = evaluate(M, prop("p_stand_1", claimed=100))
    assert d.verdict == "BLOCK" and has(d, "claimed")

def test_young_merchant_needs_review():
    m2 = replace(M, allowed_merchants=M.allowed_merchants + ("freshgear",))
    assert evaluate(m2, prop("p_mat")).verdict == "REVIEW"

def test_near_cap_needs_review():
    assert evaluate(M, prop("p_converter")).verdict == "REVIEW"

def test_unknown_product_blocked():
    assert evaluate(M, Proposal("p_nope", 1, 100)).verdict == "BLOCK"