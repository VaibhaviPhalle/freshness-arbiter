"""Stage 2: fan one question out across pinned providers through Telem.

Auto-routing stays OFF here on purpose: routing narrows each query to the
'best' few engines, and we need several independent engines to disagree.
"""
from collections import defaultdict

from telem import Telem

PROVIDERS = ["exa", "tavily", "brave", "perplexity", "parallel", "you", "ceramic", "seltz"]
PER_PROVIDER = 3      # unique results kept per provider for the LLM (speed)
SNIPPET_CHARS = 250
# Self-reported profiles are not evidence (anyone can claim "CEO at NVIDIA").
BLOCKED_URL_PARTS = ("linkedin.com/in/", "linkedin.com/pub/")


def fan_out(queries: list[str], goal: str, session: str | None = None) -> dict:
    """Returns {session_id, by_provider: {provider: [result,...]}, failed: {provider: error}}."""
    with Telem() as client:  # TELEM_API_KEY + TELEM_BASE_URL from env
        resp = client.search(
            queries,
            providers_include=PROVIDERS,
            tier="extended",          # adds publish_date
            num_results=5,
            goal=None if session else goal,
            session=session,
        )

    by_provider: dict[str, list[dict]] = defaultdict(list)
    seen: dict[str, set] = defaultdict(set)
    failed: dict[str, str] = {}

    for run in resp.by_provider:
        if run.status != "succeeded":
            failed[run.provider] = str(run.error)[:200]
            continue
        for r in run.results:
            if not r.url or r.url in seen[run.provider] or len(by_provider[run.provider]) >= PER_PROVIDER:
                continue
            if any(bad in r.url for bad in BLOCKED_URL_PARTS):
                continue
            seen[run.provider].add(r.url)
            by_provider[run.provider].append({
                "title": r.title or "",
                "url": r.url,
                "date": str(r.publish_date)[:10] if r.publish_date else None,
                "snippet": (r.content or "")[:SNIPPET_CHARS].replace("\n", " "),
                "query": run.query,
            })

    return {"session_id": resp.session_id, "by_provider": dict(by_provider), "failed": failed}
