"""Shared fixtures: a valid draft per section and an offline Editor context (no network, no model)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from xplorekit.agents import editor_verifier as editor  # noqa: E402

LONG = "A short note about the tool that explains in plain words what it does and who it helps, written by hand for this test. "

DRAFTS = {
    "money": {"title": "Get paid to rate AI chatbot answers", "audience": "Anyone with spare hours and good reading skills.",
              "summary": "Rate and correct chatbot answers on platforms that pay for it. Pay and availability depend on the platform.",
              "workflow_steps": ["Create an account on a platform", "Pass the qualification test", "Pick tasks and follow the guidelines", "Get paid by the platform's schedule"],
              "tools_and_prompts": ["Platform account", "Style guide from the platform"],
              "income": {"stated_in_source": True, "low": 15, "high": 25, "currency": "USD", "period": "hour", "basis": "The platform's own published pay range."},
              "time_to_first_result": "Days to weeks, after approval", "difficulty": "easy",
              "risks": ["Work is not guaranteed", "Pay varies by project"], "models": ["chatgpt", "claude"],
              "source_url": "https://example.com/money", "source_urls": ["https://example.com/money"]},
    "prompts": {"title": "Turn meeting notes into action items", "prompt": "You are an operations assistant. Read the notes in [NOTES] and list every action item with an owner, a due date and the decision it came from. Ask me when anything is unclear.",
                "models": ["chatgpt", "claude", "gemini"], "use_case": "business", "example_output_summary": "A table of action items with owners and due dates, followed by open questions.",
                "tags": ["meetings", "productivity"], "source_url": "https://example.com/prompt", "source_urls": ["https://example.com/prompt"]},
    "extensions": {"name": "Example Summarizer", "summary": "Summarises the page you are reading into a few bullet points using an AI service.",
                   "audience": "Readers who skim long articles.", "pros": ["One click summaries"], "cons": ["Sends page text to a server"], "pricing": "freemium",
                   "pricing_note": "", "ai_related": True, "store_url": "https://chromewebstore.google.com/detail/example-summarizer/abcdefghijklmnopabcdefghijklmnop",
                   "extension_last_updated": "unknown", "alternatives": [], "source_url": "https://example.com/ext", "source_urls": ["https://example.com/ext"]},
    "skills": {"name": "example-skill", "summary": "A skill that teaches Claude to write release notes from a changelog in a fixed house style.",
               "install_steps": ["Clone the repository", "Copy the skill folder into your skills directory"], "repo_url": "https://github.com/example/example-skill",
               "example_use_case": "Turn a messy changelog into clean release notes before a launch.", "skill_type": "claude-skill",
               "source_url": "https://github.com/example/example-skill", "source_urls": ["https://github.com/example/example-skill"]},
}
SOURCE_TEXT = {"money": "Rate chatbot answers. Pay range is 15 to 25 per hour on the platform. Tasks vary and availability changes. Platform account and style guide needed.",
               "prompts": "meeting notes action items owners due dates",
               "extensions": "Example Summarizer summarises the page you are reading into bullet points with an AI service. Freemium.",
               "skills": "example-skill writes release notes from a changelog in a house style for Claude skills."}


def ctx(section, text=None, link=("ok", 200), fact=None, **kw):
    return editor.Context(snippets={}, link_check=lambda u: link, fetch_text=lambda u: text if text is not None else SOURCE_TEXT[section],
                          fact_check=fact, fact_check_name="test", **kw)


def good_verdict(*_):
    return {"supported": True, "score": 90, "issues": []}
