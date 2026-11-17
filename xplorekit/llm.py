"""One small interface for the language model, three back ends:
  claude_cli  - the `claude` CLI (Claude Code) authenticated by CLAUDE_CODE_OAUTH_TOKEN (then _2, _3 as fallbacks when one fails or is
                out of usage); what GitHub Actions uses. The pipeline needs no Claude account beyond these tokens.
  anthropic   - the Messages API with ANTHROPIC_API_KEY
  none        - no model: agents are skipped; the Verifier still runs on drafts supplied with --drafts-file
Pick one with XK_LLM=claude_cli|anthropic|none, or leave it unset to auto-detect.
"""
import json
import os
import re
import shutil
import subprocess
import urllib.request

from xplorekit.common import settings


class LLMError(RuntimeError):
    pass


TOKEN_VARS = ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN_2", "CLAUDE_CODE_OAUTH_TOKEN_3")
STATS = {"calls": 0, "failures": 0, "token_slots_used": [], "tokens": {}}  # no secrets, only slot numbers and counts; recorded in data/runs.json for the dashboard


def reset_stats():
    STATS.update({"calls": 0, "failures": 0, "token_slots_used": [], "tokens": {}})


def record_usage(usage, turns=1, cost=None):
    """Add one model reply's token counts to the run totals. Tokens are exact; cost is what the same work would cost on the API (a plan is not billed per token)."""
    usage = usage if isinstance(usage, dict) else {}
    t = STATS.setdefault("tokens", {})
    for key, src in (("input", "input_tokens"), ("output", "output_tokens"), ("cache_read", "cache_read_input_tokens"), ("cache_creation", "cache_creation_input_tokens")):
        v = usage.get(src)
        t[key] = t.get(key, 0) + (v if isinstance(v, int) else 0)
    t["turns"] = t.get("turns", 0) + (turns if isinstance(turns, int) else 1)
    if isinstance(cost, (int, float)):
        t["cost_usd"] = round(t.get("cost_usd", 0) + cost, 4)


def token_slots():
    return [(i + 1, os.environ[v]) for i, v in enumerate(TOKEN_VARS) if os.environ.get(v)]


def provider():
    forced = os.environ.get("XK_LLM", "").strip().lower()
    if forced:
        return forced
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if token_slots() and shutil.which("claude"):
        return "claude_cli"
    return "none"


def available():
    return provider() != "none"


def complete(prompt, system=""):
    p = provider()
    model = os.environ.get("XK_MODEL") or settings().get("llm", {}).get("model", "claude-sonnet-5-5")
    if p == "anthropic":
        body = json.dumps({"model": model, "max_tokens": settings().get("llm", {}).get("max_tokens", 4000), "system": system,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
        req = urllib.request.Request(f"{base}/v1/messages", data=body, headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read())
        except Exception as e:
            raise LLMError(f"Anthropic API call failed: {e}") from e
        record_usage(data.get("usage"))
        return "".join(b.get("text", "") for b in data.get("content", []))
    if p == "claude_cli":
        cmd = ["claude", "-p", "--output-format", "json", "--model", model, "--max-turns", "1"]
        if system:
            cmd += ["--append-system-prompt", system]
        errors = []
        for slot, token in token_slots():  # first token that works wins; a failing one (limit, expiry) hands over to the next
            STATS["calls"] += 1
            try:
                r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=600, env={**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": token})
            except (OSError, subprocess.TimeoutExpired) as e:
                STATS["failures"] += 1
                errors.append(f"slot {slot}: {type(e).__name__}")
                continue
            if r.returncode != 0:
                STATS["failures"] += 1
                errors.append(f"slot {slot}: exit {r.returncode}")
                continue
            if slot not in STATS["token_slots_used"]:
                STATS["token_slots_used"].append(slot)
            try:
                data = json.loads(r.stdout)
            except ValueError:
                return r.stdout
            if isinstance(data, dict):
                record_usage(data.get("usage"), data.get("num_turns", 1), data.get("total_cost_usd"))
                return data.get("result", "")
            return r.stdout
        raise LLMError("claude CLI failed on every token: " + "; ".join(errors or ["no token set"]))
    raise LLMError("no language model configured (set CLAUDE_CODE_OAUTH_TOKEN with the claude CLI, or ANTHROPIC_API_KEY)")


def extract_json(text, expect=None):
    """Pull the first complete JSON value out of a model reply (tolerates code fences and chatter around it).
    expect="object" or "array" insists on that kind; otherwise whichever opens first wins. A verdict such as
    {"issues": []} must come back as the object, not as the empty list inside it."""
    text = re.sub(r"```(?:json)?", "", text)
    decoder = json.JSONDecoder()
    wanted = {"object": "{", "array": "["}.get(expect, "{[")
    for i, ch in enumerate(text):
        if ch in wanted:
            try:
                value, _ = decoder.raw_decode(text[i:])
            except ValueError:
                continue
            return value
    raise LLMError("model reply contained no valid JSON" + (f" ({expect})" if expect else ""))
