"""Stage 5-6: settle a conflict with event dates and primary sources, then judge.

Key idea: a page's publish date is NOT the date of the fact it states
(a release-notes page updated yesterday can still surface last year's entry).
So for every competing answer we look up WHEN that answer became true.
"""
import os
import re

from telem import Telem

from llm import ask_json

MAX_CANDIDATES = 4
PAGE_WINDOW = 1500


def _window(text: str, needle: str) -> str:
    """Excerpt of a page around the first mention of the candidate answer."""
    if not text:
        return ""
    words = [w for w in re.split(r"\W+", needle.lower()) if len(w) > 2]
    low = text.lower()
    hits = [low.find(w) for w in words if low.find(w) >= 0]
    i = min(hits) if hits else 0
    return text[max(0, i - PAGE_WINDOW // 2): i + PAGE_WINDOW].replace("\n", " ")


def _candidates(claims: list[dict], groups: list[dict]) -> list[dict]:
    by_provider = {c["provider"]: c for c in claims}
    out = []
    for g in groups[:MAX_CANDIDATES]:
        support = [by_provider[p] for p in g["providers"] if p in by_provider]
        best = max(support, key=lambda c: (c.get("date") or "", bool(c.get("url"))), default={})
        out.append({"answer": best.get("normalized") or g["answer"], "providers": g["providers"],
                    "url": best.get("url"), "evidence": best.get("evidence")})
    return out


def _event_dates(cands: list[dict], fact: str, session: str) -> dict:
    """Telem search, same session, auto-routing ON: here we want the best engines, not diversity."""
    queries = [f"{c['answer']} release date announced" if "release" in fact or "model" in fact or "version" in fact
               else f"{c['answer']} {fact} since when" for c in cands]
    with Telem() as client:
        resp = client.search(queries, auto_routing="accuracy", tier="extended", num_results=3, session=session)
    found = {c["answer"]: [] for c in cands}
    for run in resp.by_provider:
        if run.status != "succeeded":
            continue
        idx = run.batch_index if run.batch_index is not None else 0
        if idx >= len(cands):
            continue
        for r in run.results[:3]:
            found[cands[idx]["answer"]].append({
                "provider": run.provider, "url": r.url, "title": r.title,
                "date": str(r.publish_date)[:10] if r.publish_date else None,
                "snippet": (r.content or "")[:250].replace("\n", " ")})
    return found


def _fetch_pages(cands: list[dict], session: str) -> dict:
    urls = list(dict.fromkeys(c["url"] for c in cands if c.get("url")))[:5]
    if not urls:
        return {}
    with Telem() as client:
        resp = client.fetch(urls, inline_content=True, inline_max_chars=20000, session=session)
    # Match by batch position: Telem may return a canonical URL that differs from the one sent.
    pages = {}
    for i, r in enumerate(resp.results):
        idx = r.batch_index if getattr(r, "batch_index", None) is not None else i
        if idx < len(urls):
            pages[urls[idx]] = r
    out = {}
    for c in cands:
        page = pages.get(c.get("url"))
        if page and page.status == "succeeded" and page.content:
            out[c["answer"]] = {"url": page.url, "fetched_by": page.provider,
                                "excerpt": _window(page.content, c["answer"])}
        elif page:
            out[c["answer"]] = {"url": page.url, "error": str(page.error)[:150]}
    return out


def _official_source(domain: str | None, cands: list[dict], fact: str) -> dict:
    """Tavily: map the official site, then extract the parts that mention each candidate.
    Optional: skipped when there is no TAVILY_API_KEY or no official domain."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key or not domain:
        return {}
    from tavily import TavilyClient
    client = TavilyClient(api_key=key)
    try:
        site = client.map(f"https://{domain}", instructions=f"Pages announcing or documenting: {fact}",
                          max_depth=2, limit=25, timeout=25)
        urls = site.get("results", [])
        terms = {w for c in cands for w in re.split(r"\W+", c["answer"].lower()) if len(w) > 2}
        ranked = sorted(urls, key=lambda u: -sum(t in u.lower() for t in terms))[:3]
        if not ranked:
            return {}
        ext = client.extract(ranked, query=f"{fact}: {', '.join(c['answer'] for c in cands)}",
                             chunks_per_source=3, timeout=25)
        return {"domain": domain, "pages": [{"url": r["url"], "excerpt": r.get("raw_content", "")[:1500]}
                                            for r in ext.get("results", [])]}
    except Exception as e:  # never let the optional step break the run
        return {"domain": domain, "error": str(e)[:150]}


def resolve(question: str, plan: dict, claims: list[dict], groups: list[dict], session: str, today: str) -> dict:
    cands = _candidates(claims, groups)
    dates = _event_dates(cands, plan["fact"], session)
    pages = _fetch_pages(cands, session)
    official = _official_source(plan.get("official_domain"), cands, plan["fact"])

    import json
    judged = ask_json(f"""Today is {today}. Question: "{question}" (fact: {plan['fact']}).
Search providers disagree. Decide which answer is correct NOW, using the evidence below.

IMPORTANT: a page's publish date is not the date of the fact. Use the date each answer
became true (release, appointment, announcement). An older answer that has been superseded is "stale".
If two answers are both current but answer different readings of the question
(e.g. two product lines), mark both "current" and set "ambiguous": true.

Candidates (answer, which providers claimed it, their best source):
{json.dumps(cands, ensure_ascii=False)}

Event-date search results per candidate:
{json.dumps(dates, ensure_ascii=False)}

Fetched source pages per candidate:
{json.dumps(pages, ensure_ascii=False)}

Official site evidence (may be empty):
{json.dumps(official, ensure_ascii=False)}

Return JSON:
{{"answer": "the best current answer",
  "confidence": "high | medium | low",
  "ambiguous": true/false,
  "ambiguity_note": "one sentence or null",
  "candidates": [{{"answer": "...", "event_date": "YYYY-MM-DD or null", "status": "current | stale | unverified",
                   "why": "max 20 words", "source_url": "url backing the date"}}],
  "summary": "2-3 sentences for the user: the answer, which providers were stale and why, with dates"}}""",
                      model="sonnet")

    status_of = {c["answer"].lower(): c["status"] for c in judged.get("candidates", [])}
    stale = sorted({p for cand in cands if status_of.get(cand["answer"].lower()) == "stale" for p in cand["providers"]})
    return {"candidates": cands, "event_dates": dates, "pages": pages, "official": official,
            "verdict": judged, "stale_providers": stale, "status_of": status_of}
