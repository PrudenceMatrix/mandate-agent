import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB = os.getenv("LEDGER_DB", "ledger.db")
CHECK = ("product_id", "quantity", "claimed_cents", "total_cents",
         "merchant_id", "verdict", "order_id", "status")

LEDGER_SQL = """CREATE TABLE IF NOT EXISTS ledger(
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, goal TEXT, product_id TEXT,
    product TEXT, quantity INTEGER, claimed_cents INTEGER, total_cents INTEGER,
    merchant_id TEXT, verdict TEXT, reasons TEXT, order_id TEXT, status TEXT)"""
AUDIT_SQL = """CREATE TABLE IF NOT EXISTS audit(
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, ledger_id INTEGER,
    payload TEXT, prev_hash TEXT, row_hash TEXT)"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _c():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


@contextmanager
def _tx():
    c = sqlite3.connect(DB, isolation_level=None, timeout=15)
    c.row_factory = sqlite3.Row
    try:
        c.execute("BEGIN IMMEDIATE")
        yield c
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK")
        raise
    finally:
        c.close()


def _hash(prev, ts, kind, ledger_id, body):
    return hashlib.sha256(f"{prev}|{ts}|{kind}|{ledger_id}|{body}".encode()).hexdigest()


def _audit(c, kind, ledger_id, payload):
    last = c.execute("SELECT row_hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    prev = last["row_hash"] if last else "GENESIS"
    ts, body = _now(), json.dumps(payload, sort_keys=True)
    c.execute("INSERT INTO audit(ts,kind,ledger_id,payload,prev_hash,row_hash) VALUES(?,?,?,?,?,?)",
              (ts, kind, ledger_id, body, prev, _hash(prev, ts, kind, ledger_id, body)))


def init():
    with _tx() as c:
        c.execute(LEDGER_SQL)
        c.execute(AUDIT_SQL)
        if not c.execute("SELECT 1 FROM audit").fetchone():  # baseline any pre-existing rows
            for r in c.execute("SELECT * FROM ledger ORDER BY id").fetchall():
                _audit(c, "DECISION", r["id"], {k: r[k] for k in CHECK})


def add(**r):
    r["ts"] = _now()
    with _tx() as c:
        cur = c.execute(f"INSERT INTO ledger({','.join(r)}) VALUES({','.join('?' * len(r))})",
                        list(r.values()))
        _audit(c, "DECISION", cur.lastrowid, {k: r.get(k) for k in CHECK})


def set_status(order_id, status):
    with _tx() as c:
        row = c.execute("SELECT id FROM ledger WHERE order_id=?", (order_id,)).fetchone()
        if row:
            c.execute("UPDATE ledger SET status=? WHERE id=?", (status, row["id"]))
            _audit(c, "STATUS", row["id"], {"status": status})


def get_by_order(order_id):
    with _c() as c:
        row = c.execute("SELECT * FROM ledger WHERE order_id=?", (order_id,)).fetchone()
    return dict(row) if row else None


def all_rows():
    with _c() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM ledger ORDER BY id DESC")]
    for r in rows:
        r["reasons"] = json.loads(r["reasons"] or "[]")
    return rows


def spent_cents():
    with _c() as c:
        return c.execute("SELECT COALESCE(SUM(total_cents),0) FROM ledger "
                         "WHERE status='CAPTURED'").fetchone()[0]


def reset():
    with _tx() as c:
        c.execute("DELETE FROM ledger")
        c.execute("DELETE FROM audit")


def verify():
    """Recompute the hash chain, then replay it and compare with the live ledger."""
    with _c() as c:
        events = c.execute("SELECT * FROM audit ORDER BY id").fetchall()
        rows = {r["id"]: dict(r) for r in c.execute("SELECT * FROM ledger")}
    prev, state = "GENESIS", {}
    for e in events:
        if e["prev_hash"] != prev or e["row_hash"] != _hash(prev, e["ts"], e["kind"], e["ledger_id"], e["payload"]):
            return {"ok": False, "chain_ok": False, "events": len(events), "head": prev,
                    "problems": [f"Audit chain broken at event #{e['id']}"]}
        prev = e["row_hash"]
        p = json.loads(e["payload"])
        if e["kind"] == "DECISION":
            state[e["ledger_id"]] = p
        else:
            state.setdefault(e["ledger_id"], {}).update(p)
    problems = []
    for lid, want in state.items():
        got = rows.get(lid)
        if got is None:
            problems.append(f"Ledger row #{lid} was deleted")
            continue
        bad = [k for k in CHECK if want.get(k) != got.get(k)]
        if bad:
            problems.append(f"Ledger row #{lid} was altered ({', '.join(bad)} differ from the audit chain)")
    problems += [f"Ledger row #{lid} has no audit record" for lid in rows.keys() - state.keys()]
    return {"ok": not problems, "chain_ok": True, "events": len(events), "head": prev,
            "problems": problems}


def tamper():
    """Demo only: edit a ledger row directly, the way an attacker with database access would."""
    with _tx() as c:
        row = (c.execute("SELECT id FROM ledger WHERE verdict='BLOCK' ORDER BY id DESC LIMIT 1").fetchone()
               or c.execute("SELECT id FROM ledger ORDER BY id DESC LIMIT 1").fetchone())
        if not row:
            return None
        c.execute("UPDATE ledger SET verdict='ALLOW', status='CAPTURED', total_cents=1 WHERE id=?",
                  (row["id"],))
        return row["id"]
