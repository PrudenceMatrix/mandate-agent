import json, sqlite3
from datetime import datetime, timezone

DB = "ledger.db"


def _c():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _c() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS ledger(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, goal TEXT, product_id TEXT,
            product TEXT, quantity INTEGER, claimed_cents INTEGER, total_cents INTEGER,
            merchant_id TEXT, verdict TEXT, reasons TEXT, order_id TEXT, status TEXT)""")


def add(**r):
    r["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cols = ",".join(r)
    with _c() as c:
        c.execute(f"INSERT INTO ledger({cols}) VALUES({','.join('?' * len(r))})", list(r.values()))


def set_status(order_id, status):
    with _c() as c:
        c.execute("UPDATE ledger SET status=? WHERE order_id=?", (status, order_id))


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
    with _c() as c:
        c.execute("DELETE FROM ledger")