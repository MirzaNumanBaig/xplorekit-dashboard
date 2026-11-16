"""Skills Scout: writes draft entries for the 'skills' section. The prompt lives in xplorekit/prompts/skills_scout.md (edit that to change behaviour)."""
from . import base

NAME = "Skills Scout"
SECTION = "skills"
PROMPT_FILE = "skills_scout.md"


def run(candidates, n):
    return base.run(PROMPT_FILE, SECTION, candidates, n)
