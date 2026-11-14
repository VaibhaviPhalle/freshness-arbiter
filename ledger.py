"""Staleness ledger: which provider was stale, on which kind of question."""
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).with_name("ledger.db")


def _conn():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS outcomes (
        ts REAL, question TEXT, category TEXT, provider TEXT, outcome TEXT, answer TEXT)""")
    return con


def record(question: str, category: str, claims: list[dict], failed: dict, status_of: dict, overall: str):
    """outcome per provider: fresh | stale | no_answer | failed."""
    rows = []
    for c in claims:
        norm = (c.get("normalized") or "").strip().lower()
        if not norm:
            outcome = "no_answer"
        elif overall == "confirmed":
            outcome = "fresh"
        else:
            outcome = "stale" if status_of.get(norm) == "stale" else "fresh"
        rows.append((time.time(), question, category, c["provider"], outcome, c.get("normalized")))
    rows += [(time.time(), question, category, p, "failed", None) for p in failed]
    with _conn() as con:
        con.executemany("INSERT INTO outcomes VALUES (?,?,?,?,?,?)", rows)


def scoreboard() -> list[dict]:
    """Per provider and category: answered, stale count, stale rate."""
    with _conn() as con:
        rows = con.execute("""
            SELECT provider, category,
                   SUM(outcome IN ('fresh','stale')) AS answered,
                   SUM(outcome = 'stale') AS stale,
                   SUM(outcome = 'no_answer') AS no_answer
            FROM outcomes GROUP BY provider, category ORDER BY provider, category""").fetchall()
    return [{"provider": p, "category": c, "answered": a, "stale": s, "no_answer": n,
             "stale_rate": round(s / a, 2) if a else None} for p, c, a, s, n in rows]
