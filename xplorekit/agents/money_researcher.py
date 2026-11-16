"""Money Ideas Researcher: writes draft entries for the 'money' section. The prompt lives in xplorekit/prompts/money_researcher.md (edit that to change behaviour)."""
from . import base

NAME = "Money Ideas Researcher"
SECTION = "money"
PROMPT_FILE = "money_researcher.md"


def run(candidates, n):
    return base.run(PROMPT_FILE, SECTION, candidates, n)
