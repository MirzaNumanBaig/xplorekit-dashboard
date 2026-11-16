"""Prompt Hunter: writes draft entries for the 'prompts' section. The prompt lives in xplorekit/prompts/prompt_hunter.md (edit that to change behaviour)."""
from . import base

NAME = "Prompt Hunter"
SECTION = "prompts"
PROMPT_FILE = "prompt_hunter.md"


def run(candidates, n):
    return base.run(PROMPT_FILE, SECTION, candidates, n)
