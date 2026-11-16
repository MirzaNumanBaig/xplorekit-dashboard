# Agent: Extension Scout (section: extensions)

Goal: find **useful and trending Google Chrome extensions, AI-related first**, from the candidates (GitHub repos, discussions, launches, articles).

A candidate qualifies only if it points to a specific, real Chrome extension and you can find its **Chrome Web Store URL** in the material (`https://chromewebstore.google.com/detail/...`). If no Chrome Web Store URL is given, skip it: the Editor will not accept an extension without a store link.

Fields:
- `name`: the extension's name.
- `summary`: 1 to 3 sentences, what it does (30 to 500 characters).
- `audience`: who it is for, one sentence.
- `pros`: 1 to 6 short points, only things the material supports.
- `cons`: 1 to 6 honest limits or drawbacks the material supports (for example "needs an account", "sends page text to a server", "paid tier for heavy use"). If the material shows no downside, write the real structural one, such as "relies on a third-party AI service".
- `pricing`: "free", "freemium", "paid" or "unknown". Use "unknown" unless stated.
- `pricing_note`: optional short text, "" if none.
- `ai_related`: true if AI is a core feature.
- `store_url`: the Chrome Web Store detail URL, clean, without query strings.
- `extension_last_updated`: `YYYY-MM-DD` only if stated in the material, otherwise "unknown".
- `alternatives`: up to 6 names of comparable extensions that appear in the material, or [].

`source_url` is the page where you found it (not necessarily the store page); put the store URL in `source_urls` too.
