"""One research agent per section. Add a section: create a module here with SECTION/PROMPT_FILE/run(), register it below."""
from . import extension_scout, money_researcher, prompt_hunter, skills_scout

AGENTS = {m.SECTION: m for m in (money_researcher, prompt_hunter, extension_scout, skills_scout)}
