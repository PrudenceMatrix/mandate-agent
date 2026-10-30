from dataclasses import dataclass


@dataclass(frozen=True)
class Merchant:
    id: str
    name: str
    domain: str
    domain_age_days: int


@dataclass(frozen=True)
class Product:
    id: str
    title: str
    description: str
    price_cents: int
    category: str
    merchant_id: str


@dataclass(frozen=True)
class Mandate:
    budget_cents: int
    max_per_order_cents: int
    allowed_categories: tuple[str, ...]
    allowed_merchants: tuple[str, ...]
    spent_cents: int = 0


@dataclass(frozen=True)
class Proposal:
    product_id: str
    quantity: int
    claimed_total_cents: int  # what the agent SAYS it costs; never trusted


@dataclass
class Decision:
    verdict: str  # ALLOW | REVIEW | BLOCK
    reasons: list[str]
    total_cents: int = 0
    merchant_id: str = ""