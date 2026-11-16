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
STATS = {"calls": 0, "failures": 0, "token_slots_used": []}  # no secrets, only slot numbers; recorded in data/runs.json for the dashboard


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
                return json.loads(r.stdout).get("result", "")
            except ValueError:
                return r.stdout
        raise LLMError("claude CLI failed on every token: " + "; ".join(errors or ["no token set"]))
    raise LLMError("no language model configured (set CLAUDE_CODE_OAUTH_TOKEN with the claude CLI, or ANTHROPIC_API_KEY)")


def extract_json(text):
    """Pull the first JSON array/object out of a model reply (tolerates code fences and chatter around it)."""
    text = re.sub(r"```(?:json)?", "", text)
    for opener, closer in (("[", "]"), ("{", "}")):
        i, j = text.find(opener), text.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except ValueError:
                continue
    raise LLMError("model reply contained no valid JSON")
