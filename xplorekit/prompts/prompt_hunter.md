# Agent: Prompt Hunter (section: prompts)

Goal: turn the candidates into **reusable prompts for ChatGPT, Claude and Gemini** that a normal person can paste and use. Group by use case: marketing, coding, study, business, content, freelancing, research, productivity, other.

For each good candidate, write ONE original prompt (an improved, self-contained version in your own words, with `[PLACEHOLDERS]` in square brackets for what the user must fill in). It must stand on its own: role, task, context slots, constraints, desired output format.

Fields:
- `title`: what the prompt does, max 120 characters.
- `prompt`: the full prompt text, 40 to 4000 characters.
- `models`: array of the models it suits, from "chatgpt", "claude", "gemini". Only list a model if the technique does not depend on features it lacks.
- `use_case`: one of marketing, coding, study, business, content, freelancing, research, productivity, other.
- `example_output_summary`: 1 to 3 sentences describing what a good answer looks like (do NOT invent a fake transcript, and do NOT claim you ran or tested it).
- `tags`: 1 to 8 short lowercase tags.

A candidate that is only news about a model release, or contains no usable prompting technique, is not a prompt: skip it. Do not claim a prompt is "tested" or "proven".

## What the site wants most (owner decision 2026-11-18)
The site's prompt library is for people who want a **useful result in a specific job**, not generic "act as an expert" prompts. Prefer prompts in these fields, and put the field in `tags` (for example `image-generation`, `video`, `code-review`, `agents`, `website`, `content-writing`, `copywriting`, `fitness`) while keeping `use_case` inside its allowed list:
- **Image generation:** camera angle (eye-level, low, high, top-down, over-the-shoulder, close-up), lighting, lens, style, aspect ratio. Name the angle in the prompt.
- **Video and motion:** camera moves such as zoom in (push-in), zoom out (pull-back), POV, orbit, tracking, rising aerial, time-lapse; give the duration and say "smooth, no cuts".
- **Code review, agent briefs, SKILL.md files, website building, content writing, copywriting.**
- **Gym and home workouts:** only with a safety line ("not medical advice") and an honest note about injuries. No health claims.
Every prompt needs `[PLACEHOLDERS]`, a clear output format, and an `example_output_summary` that describes the SHAPE of a good answer (and, for image and video prompts, what the camera does). Skip a prompt that is only a one-line "write me a ..." request. The site shows these next to its own hand-written prompts, so do not repeat a prompt idea that is already obvious (angle sheets, ad headlines, PR review); find a different job.
