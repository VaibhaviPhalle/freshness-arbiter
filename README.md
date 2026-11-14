# Freshness Arbiter

**When search engines disagree, find out which one is out of date, and why.**

Built at SearchHack (Nov 14, 2026) on [Telem](https://telem.ai) multi-provider search, with Tavily and Claude.

## The problem

AI agents trust whatever their search engine returns. But every engine indexes the web at a different speed. For anything that changes (a new CEO, a new release, last night's result, an interest rate), engines quietly disagree, and the agent never knows it picked the stale one.

We asked 8 engines the same questions on Nov 14, 2026:

| Question | What engines said |
|---|---|
| Who is the CEO of NVIDIA? (changed Nov 12) | Some still said Jensen Huang; others had the interim CEO, Colette Kress |
| Who won the most recent World Series? | Brewers (2026), Dodgers (2025), Yankees, depending on the engine |
| Latest Claude model? | Fable 5.2, Opus 5.5, Opus 4.7 |
| Latest iPhone? | iPhone Duo, iPhone 18 Pro, iPhone 17 |

## What it does

```
1. Understand        Claude    Is the fact time-sensitive? What exactly is asked? Which queries?
2. Search 8 engines  Telem     One batched call, providers pinned, auto-routing OFF, publish dates on
3. Extract claims    Claude    One normalized answer per engine, with its source URL
4. Detect conflicts  Python    Group engines by answer: confirmed or conflict
5. Date the facts    Telem     Event-date searches (auto-routing ON) + fetch the source pages
                     Tavily    Map + extract the official site (e.g. anthropic.com, mlb.com)
6. Verdict + ledger  Claude    Current vs stale vs ambiguous, with dates; every engine's outcome logged
```

Key design choices:

- **Date the fact, not the page.** A page updated yesterday can still surface last year's answer, and a 2009 page can be right. We look up when each competing answer *became true*.
- **Disagreement is a signal, not noise.** With one engine there is nothing to compare. Telem gives us 8 engines in one call, each result tagged with its source.
- **Auto-routing off, then on.** Off when looking for conflicts (we want diversity); on when verifying (we want the best engines for that query).
- **Not every conflict is staleness.** "Latest iPhone" has two current answers (iPhone Duo and 18 Pro). The arbiter says so instead of forcing a winner.
- **Staleness ledger.** Every run records which engine was fresh, stale or silent, per question type. Over time this becomes routing data.

## How it uses Telem

| Telem feature | Where |
|---|---|
| Multi-provider search with attribution (`providers_include`, 8 engines) | Stage 2 |
| Batched queries + sessions (`goal`, `session`) | Stages 2 and 5, one trace per question |
| `tier="extended"` for `publish_date` | Stage 2 |
| `auto_routing="accuracy"` | Stage 5 event-date lookups |
| Fetch with provider fallback | Stage 5 source pages |
| Console traces | "Open Telem trace" link on every result |

## Run it

Requires Python 3.10+ and [Claude Code](https://code.claude.com) signed in (the LLM calls go through `claude -p`; `llm.py` is the single place to swap in an API client).

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install telem-sdk tavily-python streamlit pandas

export TELEM_API_KEY="tlm_..."
export TELEM_BASE_URL="https://hack.telem.ai/api/router"   # hackathon deployment
export TAVILY_API_KEY="tvly-..."                            # optional: official-site check

python cli.py "Who won the most recent World Series?"   # one question in the terminal
python bench.py                                           # fill the scoreboard + save replays
streamlit run app.py                                      # the UI
```

## Files

| File | What |
|---|---|
| `pipeline.py` | Stages 1 to 4 and the orchestrator |
| `search.py` | Telem fan-out (8 pinned engines) |
| `resolver.py` | Stage 5 to 6: event dates, Telem fetch, Tavily official check, verdict |
| `ledger.py` | SQLite staleness ledger + scoreboard |
| `llm.py` | Claude calls via Claude Code CLI |
| `app.py` | Streamlit UI (live, replay, scoreboard) |
| `cli.py`, `bench.py` | Terminal runner and benchmark |

## Limitations

- Sample sizes are small (one day of runs); the scoreboard shows a signal, not a ranking.
- About 30 to 40 seconds per question, mostly LLM time; Telem search itself takes about 4 seconds.
- Engine results vary run to run, which is the point, and also why every run is saved for replay.
