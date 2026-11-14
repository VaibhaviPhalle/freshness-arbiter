"""Claude calls through the Claude Code CLI (uses the Pro plan, no API key).

Single swap point: if API credits show up later, replace ask() with an
anthropic SDK call and nothing else changes.
"""
import json
import os
import re
import subprocess
import tempfile

SYSTEM = (
    "You are a precise information-extraction engine inside a search pipeline. "
    "You never use tools. You answer with exactly what is asked, nothing else."
)


def ask(prompt: str, model: str = "haiku", timeout: int = 180) -> str:
    # ANTHROPIC_API_KEY would switch Claude Code to paid API billing, so drop it.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    cmd = [
        "claude", "-p",
        "--model", model,
        "--output-format", "json",
        "--tools", "",
        "--system-prompt", SYSTEM,
        "--no-session-persistence",
    ]
    # Prompt goes via stdin (no argv length limits); empty cwd so no project files load.
    with tempfile.TemporaryDirectory() as cwd:
        out = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                             timeout=timeout, env=env, cwd=cwd)
    if out.returncode != 0:
        raise RuntimeError(f"claude -p failed: {out.stderr[-600:] or out.stdout[-600:]}")
    data = json.loads(out.stdout)
    if data.get("is_error"):
        raise RuntimeError(f"claude -p error: {data.get('result')}")
    return data["result"]


def ask_json(prompt: str, model: str = "haiku") -> dict | list:
    text = ask(prompt + "\n\nRespond with ONLY valid JSON. No prose, no code fences.", model)
    match = re.search(r"[\[{].*[\]}]", text, re.S)
    if not match:
        raise ValueError(f"No JSON in model output: {text[:300]}")
    return json.loads(match.group(0))
