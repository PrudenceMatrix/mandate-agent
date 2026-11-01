import os
import re
import socket
import time
from dataclasses import replace
from datetime import datetime, timezone

import requests

_CACHE: dict = {}
TTL = 3600
DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
RESERVED = (".example", ".invalid", ".test", ".local", ".localhost", ".internal")


def clean_domain(raw: str):
    d = re.sub(r"^[a-z][a-z0-9+.-]*://", "", raw.strip().lower())
    d = re.split(r"[/?#:]", d)[0]
    d = d[4:] if d.startswith("www.") else d
    return d if DOMAIN_RE.match(d) and not d.endswith(RESERVED) else None


def _rdap_age(domain: str):
    parts = domain.split(".")
    for i in range(len(parts) - 1):  # try the full name, then the parent domains
        try:
            r = requests.get(f"https://rdap.org/domain/{'.'.join(parts[i:])}", timeout=6,
                             headers={"Accept": "application/rdap+json"})
            if r.status_code != 200:
                continue
            for ev in r.json().get("events", []):
                if ev.get("eventAction") == "registration":
                    created = datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
                    return (datetime.now(timezone.utc) - created).days
            return None
        except (requests.RequestException, ValueError, TypeError):
            return None
    return None


def _verdict(age, resolves):
    if not resolves:
        return "BLOCK", ["Domain does not resolve in DNS"]
    if age is None:
        return "REVIEW", ["Registration date could not be determined"]
    if age < 30:
        return "BLOCK", [f"Domain registered only {age} days ago"]
    if age < 90:
        return "REVIEW", [f"Young domain ({age} days old)"]
    return "ALLOW", [f"Domain is {age} days old and resolves"]


def lookup(raw: str):
    d = clean_domain(raw or "")
    if not d:
        return {"domain": (raw or "")[:80], "error": "Not a valid public domain name"}
    hit = _CACHE.get(d)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    try:
        socket.getaddrinfo(d, 443)
        resolves = True
    except OSError:
        resolves = False
    age = _rdap_age(d) if resolves else None
    verdict, reasons = _verdict(age, resolves)
    out = {"domain": d, "resolves": resolves, "age_days": age, "verdict": verdict, "reasons": reasons}
    _CACHE[d] = (time.time(), out)
    return out


def refresh_merchant(m):
    """With LIVE_INTEL=1, replace a seeded domain age with a live RDAP lookup (real domains only)."""
    if os.getenv("LIVE_INTEL") != "1" or not clean_domain(m.domain):
        return m
    age = lookup(m.domain).get("age_days")
    return replace(m, domain_age_days=age) if age is not None else m
