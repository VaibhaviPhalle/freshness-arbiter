"""Run: python cli.py "What is the latest Claude model?" """
import json
import sys

from pipeline import run

question = " ".join(sys.argv[1:]) or "What is the latest stable Python release?"
out = run(question)

p = out["plan"]
print(f"\nQ: {question}")
print(f"Fact: {p['fact']}  | category: {p['category']}  | time-sensitive: {p['time_sensitive']}")
print(f"Queries: {p['queries']}")
print(f"Telem session: {out['session_id']}\n")

print(f"{'PROVIDER':11} {'ANSWER':28} {'DATE':11} URL")
for c in out["claims"]:
    print(f"{c['provider']:11} {str(c.get('normalized') or '-')[:28]:28} {str(c.get('date') or '-'):11} {c.get('url') or ''}")
for prov, err in out["failed"].items():
    print(f"{prov:11} FAILED: {err}")

v = out["conflicts"]
print(f"\nSTATUS: {v['status'].upper()}")
for g in v["groups"]:
    print(f"  {g['answer']!r:30} <- {', '.join(g['providers'])}")
res = out.get("resolution")
if res:
    v = res["verdict"]
    print(f"\nVERDICT: {v.get('answer')}   confidence: {v.get('confidence')}   ambiguous: {v.get('ambiguous')}")
    for c in v.get("candidates", []):
        print(f"  [{c.get('status'):10}] {c.get('answer'):28} happened {c.get('event_date') or '?':11} {c.get('why')}")
    if v.get("ambiguity_note"):
        print(f"  Note: {v['ambiguity_note']}")
    print(f"  Stale providers: {', '.join(res['stale_providers']) or 'none'}")
    off = res.get("official") or {}
    print(f"  Official check (Tavily): {off.get('domain') or 'skipped'} "
          f"{'pages=' + str(len(off.get('pages', []))) if off.get('pages') else off.get('error', '')}")
    print(f"\n{v.get('summary')}")

print(f"\nTimings (s): {out['timings_s']}")

with open("last_run.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print("Full output saved to last_run.json")
