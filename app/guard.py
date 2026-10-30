import re

from .catalog import MERCHANTS, PRODUCTS
from .models import Decision, Mandate, Proposal

HARD_INJECTION = [
    r"ignore\s+(all\s+|any\s+|the\s+|your\s+)?(previous|prior|above|earlier|budget|mandate|limit|rules|polic\w*|instructions?)",
    r"disregard\s+.{0,25}(budget|mandate|limit|rules|instructions?)",
    r"(override|bypass)\s+.{0,30}(budget|limit|mandate|polic\w*|guard)",
    r"(note|message|instruction)s?\s+(to|for)\s+(the\s+)?(ai|assistant|agent|llm)",
    r"\bsystem\s+prompt\b",
    r"(send|transfer|route|redirect)\s+(the\s+)?(payment|money|funds)\s+to",
    r"pre-?approved",
]
SOFT_INJECTION = [r"[\w.+-]+@[\w-]+\.[\w.-]+"]


def fmt(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def scan_listing(text: str) -> tuple[list[str], list[str]]:
    hard = [m.group(0) for p in HARD_INJECTION if (m := re.search(p, text, re.I))]
    soft = [m.group(0) for p in SOFT_INJECTION if (m := re.search(p, text, re.I))]
    return hard, soft


def evaluate(mandate: Mandate, proposal: Proposal, products=None, merchants=None) -> Decision:
    products = products or PRODUCTS
    merchants = merchants or MERCHANTS
    product = products.get(proposal.product_id)
    if product is None:
        return Decision("BLOCK", [f"Unknown product '{proposal.product_id}'"])
    merchant = merchants[product.merchant_id]
    hard: list[str] = []
    soft: list[str] = []

    if not 1 <= proposal.quantity <= 5:
        hard.append(f"Quantity {proposal.quantity} is outside the allowed range 1-5")

    total = product.price_cents * proposal.quantity
    if proposal.claimed_total_cents != total:
        hard.append(f"Agent claimed {fmt(proposal.claimed_total_cents)} "
                    f"but catalog total is {fmt(total)}")
    if product.category not in mandate.allowed_categories:
        hard.append(f"Category '{product.category}' is not allowed by the mandate")
    if merchant.id not in mandate.allowed_merchants:
        hard.append(f"Merchant '{merchant.id}' is not on the allowlist")
    if total > mandate.max_per_order_cents:
        hard.append(f"Total {fmt(total)} exceeds per-order cap "
                    f"{fmt(mandate.max_per_order_cents)}")
    remaining = mandate.budget_cents - mandate.spent_cents
    if total > remaining:
        hard.append(f"Total {fmt(total)} exceeds remaining budget {fmt(remaining)}")

    inj_hard, inj_soft = scan_listing(f"{product.title}\n{product.description}")
    hard += [f"Possible prompt injection in listing: '{h}'" for h in inj_hard]
    soft += [f"Listing contains a contact address ('{s}'), payee redirection risk"
             for s in inj_soft]

    if merchant.domain_age_days < 30:
        hard.append(f"Merchant domain is only {merchant.domain_age_days} days old")
    elif merchant.domain_age_days < 90:
        soft.append(f"Merchant domain is young ({merchant.domain_age_days} days old)")
    if total * 10 > mandate.max_per_order_cents * 8:
        soft.append("Total is above 80% of the per-order cap")

    if hard:
        return Decision("BLOCK", hard + soft, total, merchant.id)
    if soft:
        return Decision("REVIEW", soft, total, merchant.id)
    return Decision("ALLOW", ["All checks passed"], total, merchant.id)