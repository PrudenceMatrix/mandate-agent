from datetime import datetime, timedelta, timezone

import requests

from app import assess, classifier, intel
from app.agent import MANDATE
from app.models import Merchant, Proposal

OK = Proposal("p_stand_1", 1, 2499)


class FakeResp:
    ok = True
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


def test_classifier_is_off_by_default(monkeypatch):
    monkeypatch.delenv("LLM_CLASSIFIER", raising=False)
    assert classifier.second_opinion("hello") is None


def test_classifier_can_add_a_block(monkeypatch):
    monkeypatch.setattr(assess.classifier, "second_opinion",
                        lambda t: {"injection": True, "reason": "asks the agent to pay elsewhere"})
    d = assess.assess(MANDATE, OK)
    assert d.verdict == "BLOCK" and any("classifier" in r for r in d.reasons)


def test_classifier_can_never_remove_a_block(monkeypatch):
    monkeypatch.setattr(assess.classifier, "second_opinion", lambda t: {"injection": False, "reason": ""})
    assert assess.assess(MANDATE, Proposal("p_stand_poison", 1, 2100)).verdict == "BLOCK"


def test_classifier_parses_model_output(monkeypatch):
    for k, v in {"LLM_CLASSIFIER": "1", "LLM_BASE_URL": "http://x", "LLM_API_KEY": "k", "LLM_MODEL": "m"}.items():
        monkeypatch.setenv(k, v)
    body = {"choices": [{"message": {"content": 'Sure: {"injection": true, "reason": "x"}'}}]}
    monkeypatch.setattr(classifier.requests, "post", lambda *a, **k: FakeResp(body))
    assert classifier.second_opinion("text")["injection"] is True


def test_classifier_fails_open(monkeypatch):
    for k, v in {"LLM_CLASSIFIER": "1", "LLM_BASE_URL": "http://x", "LLM_API_KEY": "k", "LLM_MODEL": "m"}.items():
        monkeypatch.setenv(k, v)

    def boom(*a, **k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(classifier.requests, "post", boom)
    assert classifier.second_opinion("text") is None
    assert assess.assess(MANDATE, OK).verdict == "ALLOW"


def test_clean_domain():
    assert intel.clean_domain("https://www.Shop.com/path?x=1") == "shop.com"
    for bad in ("localhost", "127.0.0.1", "http://169.254.169.254/", "deskcraft.example", "a b.com", ""):
        assert intel.clean_domain(bad) is None


def test_lookup_scores_a_young_domain(monkeypatch):
    intel._CACHE.clear()
    monkeypatch.setattr(intel.socket, "getaddrinfo", lambda *a, **k: [1])
    ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {"events": [{"eventAction": "registration", "eventDate": ten_days_ago}]}
    monkeypatch.setattr(intel.requests, "get", lambda *a, **k: FakeResp(body))
    r = intel.lookup("brand-new-store.com")
    assert r["verdict"] == "BLOCK" and r["age_days"] == 10


def test_lookup_scores_an_old_domain(monkeypatch):
    intel._CACHE.clear()
    monkeypatch.setattr(intel.socket, "getaddrinfo", lambda *a, **k: [1])
    body = {"events": [{"eventAction": "registration", "eventDate": "2010-01-01T00:00:00Z"}]}
    monkeypatch.setattr(intel.requests, "get", lambda *a, **k: FakeResp(body))
    r = intel.lookup("old-store.com")
    assert r["verdict"] == "ALLOW" and r["age_days"] > 3000


def test_lookup_handles_dns_failure_and_rdap_outage(monkeypatch):
    intel._CACHE.clear()

    def nodns(*a, **k):
        raise OSError("no dns")
    monkeypatch.setattr(intel.socket, "getaddrinfo", nodns)
    assert intel.lookup("ghost-store.com")["verdict"] == "BLOCK"
    intel._CACHE.clear()
    monkeypatch.setattr(intel.socket, "getaddrinfo", lambda *a, **k: [1])

    def down(*a, **k):
        raise requests.ConnectionError("rdap down")
    monkeypatch.setattr(intel.requests, "get", down)
    assert intel.lookup("some-store.com")["verdict"] == "REVIEW"


def test_refresh_merchant(monkeypatch):
    seeded = Merchant("m", "M", "deskcraft.example", 5)
    real = Merchant("m", "M", "shop.com", 5)
    monkeypatch.setenv("LIVE_INTEL", "1")
    monkeypatch.setattr(intel, "lookup", lambda d: {"age_days": 3000})
    assert intel.refresh_merchant(seeded).domain_age_days == 5
    assert intel.refresh_merchant(real).domain_age_days == 3000
    monkeypatch.delenv("LIVE_INTEL")
    assert intel.refresh_merchant(real).domain_age_days == 5
