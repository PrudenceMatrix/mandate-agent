from app import attacks


def test_core_suite_is_unchanged():
    r = attacks.run_lab("core")
    assert (r["attempts"], r["blocked"], r["escalated"], r["leaked"]) == (9, 8, 1, 0)
    assert r["all_passed"]


def test_extended_suite_holds():
    r = attacks.run_lab("extended")
    assert r["leaked"] == 0 and r["all_passed"], [x for x in r["rows"] if not x["passed"]]
