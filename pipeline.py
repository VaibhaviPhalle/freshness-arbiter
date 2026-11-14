"""Freshness Arbiter, stages 1-4: understand -> fan out -> extract claims -> detect conflicts."""
import json
import time
from collections import defaultdict
from datetime import date

from ledger import record
from llm import ask_json
from resolver import resolve
from search import fan_out

TODAY = date.today().isoformat()


def understand(question: str) -> dict:
    """Stage 1: is this fact time-sensitive, what exactly is asked, which queries to run."""
    return ask_json(f"""Today is {TODAY}. A user asked: "{question}"

Return JSON:
{{"time_sensitive": true/false,   // can the correct answer change over months?
  "fact": "the single fact being asked, e.g. 'current CEO of Intel'",
  "category": "person_role | version_release | number_price | event | other",
  "queries": ["2 or 3 short web search queries, each a different angle, one should target recent change news"],
  "official_domain": "the primary-source website for this fact, e.g. 'anthropic.com', 'python.org', or null"}}""")


def extract_claims(question: str, fact: str, by_provider: dict) -> list[dict]:
    """Stage 3: one claimed answer per provider, normalized so equal answers match."""
    evidence = json.dumps(by_provider, ensure_ascii=False)
    data = ask_json(f"""Today is {TODAY}. Question: "{question}" (fact: {fact}).

Below are search results grouped by the search provider that returned them.
For EACH provider, decide what answer its results imply. Use only that provider's results.

Rules:
- "answer": the answer as that provider's results state it, or null if they do not state one.
- "normalized": a short canonical form so that identical answers from different providers
  are EXACTLY the same string (e.g. "Python 3.15", "Lip-Bu Tan", "iPhone 18"). null if no answer.
- "url": the single result URL that best supports the answer. "date": that result's date or null.
- "evidence": max 15 words copied from that provider's snippet supporting the answer.

Return JSON: {{"claims": [{{"provider": "...", "answer": ..., "normalized": ..., "url": ..., "date": ..., "evidence": ...}}]}}

Results by provider:
{evidence}""")
    return data["claims"]


def detect_conflicts(claims: list[dict]) -> dict:
    """Stage 4: plain Python. Group providers by normalized answer."""
    groups: dict[str, list[str]] = defaultdict(list)
    for c in claims:
        if c.get("normalized"):
            groups[c["normalized"].strip().lower()].append(c["provider"])
    status = "no_answer" if not groups else ("confirmed" if len(groups) == 1 else "conflict")
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    return {"status": status, "groups": [{"answer": a, "providers": p} for a, p in ordered]}


def run(question: str, on_stage=lambda name, data: None) -> dict:
    """on_stage(name, data) is called after each stage so a UI can show progress live."""
    t = {}
    t0 = time.time()
    plan = understand(question)
    t["understand"] = round(time.time() - t0, 1)
    on_stage("understand", plan)

    t0 = time.time()
    found = fan_out(plan["queries"], goal=f"Freshness arbitration: {question}")
    t["search"] = round(time.time() - t0, 1)
    on_stage("search", found)

    t0 = time.time()
    claims = extract_claims(question, plan["fact"], found["by_provider"])
    t["extract"] = round(time.time() - t0, 1)
    on_stage("extract", claims)

    verdict = detect_conflicts(claims)
    on_stage("conflicts", verdict)

    resolution = None
    if verdict["status"] == "conflict":
        t0 = time.time()
        resolution = resolve(question, plan, claims, verdict["groups"], found["session_id"], TODAY)
        t["resolve"] = round(time.time() - t0, 1)
        on_stage("resolve", resolution)

    record(question, plan.get("category", "other"), claims, found["failed"],
           resolution["status_of"] if resolution else {}, verdict["status"])

    return {"question": question, "plan": plan, "session_id": found["session_id"],
            "failed": found["failed"], "claims": claims, "conflicts": verdict,
            "resolution": resolution, "timings_s": t, "evidence": found["by_provider"]}
