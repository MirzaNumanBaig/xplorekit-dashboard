# Agent: Skills Scout (section: skills)

Goal: find **Claude Skills (folders containing a SKILL.md) and closely related agent skills** worth listing: useful, maintained, clearly documented, with a public source repo.

Fields:
- `name`: skill or collection name.
- `summary`: 1 to 3 sentences on what it does (30 to 500 characters).
- `install_steps`: 1 to 8 short, concrete steps. Use only steps the repository or docs in the material actually describe (for example "Clone the repo", "Copy the skill folder into your skills directory", "Ask Claude to use it by name"). If the material gives no install information, write the single honest step "See the repository README for install steps" and nothing invented.
- `repo_url`: the public GitHub repo URL (or official docs URL).
- `example_use_case`: one concrete, realistic situation where you would use it (20 to 400 characters).
- `skill_type`: "claude-skill" (a SKILL.md skill), "agent-skill" (a skill for another agent/tool), or "collection" (a repo with many skills).

Skip archived projects, empty templates, marketing-only repos, and anything with no explanation of what it does.
`source_url` should be `repo_url` unless a better primary page exists.
