"""Freshness Arbiter UI.  Run: streamlit run app.py"""
import json
import os
import re
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from ledger import scoreboard
from pipeline import run

RUNS = Path(__file__).with_name("runs")
RUNS.mkdir(exist_ok=True)
CONSOLE = os.environ.get(
    "TELEM_CONSOLE_URL",
    "https://hack.telem.ai/o/b6d1dffd-c543-4cfa-a64b-e0a5f0eb026c/p/d46011fc-d1e0-4a6d-8146-3f3e38626842/traffic2",
)
EXAMPLES = [
    "Who is the CEO of NVIDIA?",
    "Who won the most recent World Series?",
    "What is the current Federal Reserve interest rate?",
    "Who won the latest Ballon d'Or?",
    "Who is the most recent Nobel Peace Prize winner?",
    "What is the latest TypeScript version?",
    "What is the latest .NET version?",
    "What is the latest Claude model released by Anthropic?",
    "What is the latest iPhone model?",
    "What is the latest stable Python release?",
]
COLORS = {"current": "#1D9E75", "stale": "#D85A30", "unverified": "#888780", "none": "#B4B2A9"}
STAGES = [("1", "Understand", "Claude"), ("2", "Search 8 engines", "Telem"), ("3", "Extract claims", "Claude"),
          ("4", "Detect conflicts", "code"), ("5", "Date the facts", "Telem + Tavily"), ("6", "Verdict + ledger", "Claude")]

st.set_page_config(page_title="Freshness Arbiter", layout="wide")
st.title("Freshness Arbiter")
st.markdown("##### Search engines index the web at different speeds. When they disagree, we find out which one is out of date, and why.")
st.markdown(" → ".join(f"**{n}. {name}** <span style='opacity:.6'>({who})</span>" for n, name, who in STAGES),
            unsafe_allow_html=True)
st.divider()


def slug(q: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")[:60]


def provider_cards(out: dict):
    status_of = (out.get("resolution") or {}).get("status_of", {})
    confirmed = out["conflicts"]["status"] == "confirmed"
    claims = out["claims"]
    cols = st.columns(4)
    for i, c in enumerate(claims):
        norm = (c.get("normalized") or "").lower()
        state = "none" if not norm else ("current" if confirmed else status_of.get(norm, "unverified"))
        label = {"current": "Fresh", "stale": "Stale", "unverified": "Unverified", "none": "No answer"}[state]
        with cols[i % 4]:
            st.markdown(
                f"<div style='border:1px solid {COLORS[state]};border-left:6px solid {COLORS[state]};"
                f"border-radius:8px;padding:10px;margin-bottom:10px'>"
                f"<b>{c['provider']}</b> <span style='float:right;color:{COLORS[state]}'>{label}</span><br>"
                f"<span style='font-size:1.1em'>{c.get('normalized') or '—'}</span><br>"
                f"<span style='font-size:0.8em;opacity:0.7'>page date: {c.get('date') or '?'}</span></div>",
                unsafe_allow_html=True)
            if c.get("url"):
                st.caption(f"[source]({c['url']})")
    for p, err in out.get("failed", {}).items():
        st.caption(f"{p}: failed ({err[:80]})")


def verdict_block(out: dict):
    res = out.get("resolution")
    groups = out["conflicts"]["groups"]
    if out["conflicts"]["status"] == "confirmed":
        st.success(f"All answering providers agree: **{groups[0]['answer']}**. No arbitration needed.")
        return
    if not res:
        st.warning("No provider stated an answer.")
        return
    v = res["verdict"]
    st.subheader(f"Verdict: {v.get('answer')}")
    st.write(f"Confidence: **{v.get('confidence')}**  ·  Stale providers: "
             f"**{', '.join(res['stale_providers']) or 'none'}**")
    if v.get("ambiguous") and v.get("ambiguity_note"):
        st.info(v["ambiguity_note"])
    st.write(v.get("summary"))
    st.markdown("**When did each answer actually become true?**")
    # Markdown table wraps long text (st.dataframe truncates the "why" column).
    icon = {"current": "🟢 current", "stale": "🔴 stale", "unverified": "⚪ unverified"}
    lines = ["| Answer | Status | Became true | Why | Source |", "|---|---|---|---|---|"]
    for c in v.get("candidates", []):
        src = f"[link]({c['source_url']})" if (c.get("source_url") or "").startswith("http") else ""
        why = (c.get("why") or "").replace("|", "/")
        lines.append(f"| {c.get('answer')} | {icon.get(c.get('status'), c.get('status'))} | "
                     f"{c.get('event_date') or '?'} | {why} | {src} |")
    st.markdown("\n".join(lines))


def evidence_block(out: dict):
    res = out.get("resolution") or {}
    with st.expander("Stage 1: query understanding"):
        st.json(out["plan"])
    with st.expander("Stage 2: raw results per provider (Telem fan-out)"):
        st.json(out["evidence"])
    if res:
        with st.expander("Stage 5a: event-date searches (Telem, auto-routing on)"):
            st.json(res["event_dates"])
        with st.expander("Stage 5b: source pages read (Telem fetch)"):
            st.json(res["pages"])
        with st.expander("Stage 5c: official site check (Tavily map + extract)"):
            st.json(res["official"] or {"skipped": "no TAVILY_API_KEY or no official domain"})


def headline(out: dict):
    """One-line takeaway + counts, so the point lands in five seconds."""
    claims = out["claims"]
    res = out.get("resolution") or {}
    stale = set(res.get("stale_providers", []))
    answered = [c for c in claims if c.get("normalized")]
    no_answer = len(claims) - len(answered) + len(out.get("failed", {}))
    status = out["conflicts"]["status"]
    if status == "conflict":
        groups = len(out["conflicts"]["groups"])
        msg = (f"⚠️ The engines gave **{groups} different answers**. "
               f"**{len(stale)} of {len(answered)}** answering engines were out of date.")
        # Plain if/else: a bare `a() if x else b()` expression gets echoed by Streamlit "magic".
        if stale:
            st.error(msg)
        else:
            st.warning(msg)
    elif status == "confirmed":
        st.success(f"✅ All {len(answered)} answering engines agree. No stale answers.")
    else:
        st.warning("No engine stated an answer.")
    a, b, c, d = st.columns(4)
    a.metric("Engines asked", len(claims) + len(out.get("failed", {})))
    b.metric("Distinct answers", len(out["conflicts"]["groups"]))
    c.metric("Out of date", len(stale))
    d.metric("No answer / failed", no_answer)


def show(out: dict):
    st.markdown(f"### {out['question']}")
    headline(out)
    t = out["timings_s"]
    reasoning = round(sum(v for k, v in t.items() if k != "search"), 1)
    st.markdown(f"**Fact:** {out['plan']['fact']}  ·  **Type:** {out['plan']['category']}  ·  "
                f"[Open Telem trace]({CONSOLE}/{out['session_id']})")
    st.caption(f"Telem search across 8 engines: {t.get('search', '?')}s  ·  "
               f"Claude reasoning + verification: {reasoning}s")
    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### What each search provider says")
        provider_cards(out)
    with right:
        verdict_block(out)
    evidence_block(out)


tab_ask, tab_board = st.tabs(["Ask", "Staleness scoreboard"])

with tab_ask:
    mode = st.radio("Mode", ["Live", "Replay a saved run"], horizontal=True)
    if mode == "Live":
        # One box: type any question, or pick an example from the list.
        try:
            question = st.selectbox(
                "Ask a question whose answer can go stale",
                EXAMPLES, index=None, accept_new_options=True,
                placeholder="Type your own question, or pick an example…",
            )
        except TypeError:  # Streamlit older than 1.45: fall back to two widgets
            pick = st.selectbox("Try an example", [""] + EXAMPLES)
            question = st.text_input("Or type your own question", value=pick)
        if st.button("Arbitrate", type="primary", disabled=not question):
            labels = {"understand": "Understood the question", "search": "Searched 8 providers through Telem",
                      "extract": "Extracted each provider's claim", "conflicts": "Compared claims",
                      "resolve": "Checked event dates, source pages and the official site"}
            with st.status("Working...", expanded=True) as status:
                t0 = time.time()
                out = run(question, on_stage=lambda name, data: st.write(f"✓ {labels[name]}"))
                status.update(label=f"Done in {time.time() - t0:.0f}s", state="complete")
            (RUNS / f"{slug(question)}.json").write_text(json.dumps(out, default=str, indent=2))
            show(out)
    else:
        saved = sorted(RUNS.glob("*.json"), key=lambda p: -p.stat().st_mtime)
        if not saved:
            st.info("No saved runs yet. Every live run is saved automatically.")
        else:
            f = st.selectbox("Saved run", saved, format_func=lambda p: json.loads(p.read_text())["question"])
            show(json.loads(f.read_text()))

with tab_board:
    rows = scoreboard()
    if not rows:
        st.info("Run a few questions (or python bench.py) to fill the scoreboard.")
    else:
        df = pd.DataFrame(rows)
        overall = (df.groupby("provider")[["answered", "stale", "no_answer"]].sum()
                   .assign(stale_rate=lambda d: (d.stale / d.answered.where(d.answered > 0)).round(2))
                   .sort_values("stale_rate", ascending=False))
        st.markdown("#### How often each provider was out of date")
        st.bar_chart(overall["stale_rate"].fillna(0))
        st.dataframe(overall, width="stretch")
        st.markdown("#### By question type")
        st.dataframe(df, hide_index=True, width="stretch")
