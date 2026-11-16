"""Extension Scout: writes draft entries for the 'extensions' section. The prompt lives in xplorekit/prompts/extension_scout.md (edit that to change behaviour)."""
from . import base

NAME = "Extension Scout"
SECTION = "extensions"
PROMPT_FILE = "extension_scout.md"


def run(candidates, n):
    return base.run(PROMPT_FILE, SECTION, candidates, n)
