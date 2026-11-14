"""Run a varied set of time-sensitive questions: fills the staleness ledger and
saves every run to runs/ so the UI can replay them.
Run: python bench.py      (about 1 minute per question)"""
import json
import re
from pathlib import Path

from ledger import scoreboard
from pipeline import run

QUESTIONS = [
    "Who is the CEO of NVIDIA?",
    "Who won the most recent World Series?",
    "What is the current Federal Reserve interest rate?",
    "Who won the latest Ballon d'Or?",
    "Who is the most recent Nobel Peace Prize winner?",
    "What is the latest TypeScript version?",
    "What is the latest .NET version?",
]

RUNS = Path(__file__).with_name("runs")
RUNS.mkdir(exist_ok=True)

for q in QUESTIONS:
    try:
        out = run(q)
        slug = re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")[:60]
        (RUNS / f"{slug}.json").write_text(json.dumps(out, default=str, indent=2))
        res = out.get("resolution")
        groups = out["conflicts"]["groups"]
        answer = res["verdict"].get("answer") if res else (groups[0]["answer"] if groups else "-")
        stale = f"  stale: {', '.join(res['stale_providers'])}" if res and res["stale_providers"] else ""
        print(f"{out['conflicts']['status']:10} {q}  ->  {answer}{stale}")
    except Exception as e:
        print(f"ERROR      {q}: {e}")

print("\nSCOREBOARD")
for row in scoreboard():
    print(f"  {row['provider']:11} {row['category']:16} answered={row['answered']} stale={row['stale']} rate={row['stale_rate']}")
