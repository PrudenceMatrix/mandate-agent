import sqlite3

from app import db


def row(**kw):
    base = dict(goal="g", product_id="p", product="P", quantity=1, claimed_cents=100, total_cents=100,
                merchant_id="m", verdict="ALLOW", reasons="[]", order_id=None, status="BLOCKED")
    base.update(kw)
    return base


def test_clean_chain_verifies():
    db.add(**row(order_id="O1", status="PENDING_APPROVAL"))
    db.set_status("O1", "CAPTURED")
    db.add(**row(verdict="BLOCK"))
    v = db.verify()
    assert v["ok"] and v["events"] == 3


def test_edited_ledger_row_is_detected():
    db.add(**row(verdict="BLOCK"))
    db.tamper()
    v = db.verify()
    assert not v["ok"] and v["chain_ok"] and any("altered" in p for p in v["problems"])


def test_deleted_ledger_row_is_detected():
    db.add(**row())
    with sqlite3.connect(db.DB) as c:
        c.execute("DELETE FROM ledger")
    assert any("deleted" in p for p in db.verify()["problems"])


def test_row_inserted_behind_the_back_is_detected():
    db.add(**row())
    with sqlite3.connect(db.DB) as c:
        c.execute("INSERT INTO ledger(ts,verdict,status,total_cents) VALUES('t','ALLOW','CAPTURED',1)")
    assert any("no audit record" in p for p in db.verify()["problems"])


def test_rewritten_audit_history_is_detected():
    db.add(**row())
    with sqlite3.connect(db.DB) as c:
        c.execute("UPDATE audit SET payload='{}'")
    assert not db.verify()["chain_ok"]


def test_existing_rows_are_baselined_on_init():
    with sqlite3.connect(db.DB) as c:
        c.execute("DELETE FROM audit")
        c.execute("INSERT INTO ledger(ts,product_id,quantity,claimed_cents,total_cents,merchant_id,"
                  "verdict,reasons,status) VALUES('t','p',1,1,1,'m','BLOCK','[]','BLOCKED')")
    db.init()
    assert db.verify()["ok"]


def test_reset_clears_both():
    db.add(**row())
    db.reset()
    assert db.all_rows() == [] and db.verify()["events"] == 0


def test_concurrent_writes_do_not_fork_the_chain():
    import threading
    ts = [threading.Thread(target=lambda i=i: db.add(**row(order_id=f"T{i}", status="PENDING_APPROVAL")))
          for i in range(25)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    v = db.verify()
    assert v["ok"] and v["events"] == 25
