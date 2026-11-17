import json
import tempfile
import unittest
from pathlib import Path

from xplorekit import site_known
from xplorekit.common import canon_key
from xplorekit.verify import dedupe

ID = "abcdefghijklmnopabcdefghijklmnop"


class IdentityTests(unittest.TestCase):
    def test_one_github_repo_whatever_the_spelling(self):
        forms = ["https://github.com/Owner/Repo", "http://www.github.com/owner/repo/", "https://github.com/owner/repo.git",
                 "https://github.com/owner/repo/blob/main/skills/x/SKILL.md?plain=1#top", "https://github.com/OWNER/REPO/tree/dev"]
        self.assertEqual({canon_key(u) for u in forms}, {"github:owner/repo"})
        self.assertNotEqual(canon_key("https://github.com/owner/repo"), canon_key("https://github.com/owner/other"))

    def test_one_chrome_extension_whatever_the_slug(self):
        forms = [f"https://chromewebstore.google.com/detail/{ID}", f"https://chromewebstore.google.com/detail/glarity/{ID}?hl=en",
                 f"https://chrome.google.com/webstore/detail/some-old-slug/{ID}", f"http://chromewebstore.google.com/detail/another-name/{ID}/reviews"]
        self.assertEqual({canon_key(u) for u in forms}, {f"cws:{ID}"})

    def test_other_urls_ignore_tracking_scheme_www_and_trailing_slash(self):
        self.assertEqual(canon_key("https://www.Example.com/a/b/?utm_source=x#frag"), canon_key("http://example.com/a/b"))
        self.assertNotEqual(canon_key("https://example.com/a"), canon_key("https://example.com/b"))

    def test_an_extension_already_on_the_site_is_caught_under_a_different_store_slug(self):
        known = [{"title": "Glarity", "urls": {canon_key(f"https://chromewebstore.google.com/detail/glarity-old-slug/{ID}")}, "where": "site page"}]
        e = {"name": "Something else entirely", "source_urls": ["https://github.com/x/y"], "store_url": f"https://chromewebstore.google.com/detail/{ID}"}
        self.assertIn("same URL", dedupe.find_duplicate(e, known))


class NearDuplicatePromptTests(unittest.TestCase):
    A = {"title": "Build a new plugin by pointing an AI coding agent at reference code", "prompt": "Act as a senior engineer. Study the reference plugin in [PATH] first, then outline the new plugin.", "source_urls": ["https://docs.example.com/a"]}
    B = {"title": "Build a new plugin by studying existing reference code first", "prompt": "You are a careful developer who reads the example in [REPO] before writing any code.", "source_urls": ["https://docs.example.com/a"]}
    C = {"title": "Define success criteria and test cases before improving a prompt", "prompt": "List three measurable success criteria and five test cases for [PROMPT] before you change a word of it.", "source_urls": ["https://docs.example.com/b"]}

    def test_the_real_near_duplicate_titles_are_caught_and_distinct_prompts_are_not(self):
        self.assertIn("same words in the title", dedupe.find_duplicate(self.B, dedupe.known_from_entries([self.A]), by_url=False))
        self.assertIsNone(dedupe.find_duplicate(self.C, dedupe.known_from_entries([self.A, self.B]), by_url=False))

    def test_different_titles_but_the_same_wording_are_caught(self):
        base = "You are a careful research assistant. Read the document in the tags and write a three sentence overview then five bullet points then list anything unclear or contradictory."
        a = {"title": "Summarise a long document", "prompt": base, "source_urls": ["https://x.com/1"]}
        b = {"title": "Condense a lengthy report", "prompt": base.replace("careful research", "diligent").replace("three sentence", "short"), "source_urls": ["https://x.com/2"]}
        self.assertIn("prompt wording overlaps", dedupe.find_duplicate(b, dedupe.known_from_entries([a]), by_url=False))

    def test_prompts_may_still_share_a_source_page(self):
        k = dedupe.known_from_entries([self.A])
        self.assertIsNone(dedupe.find_duplicate(self.C | {"source_urls": ["https://docs.example.com/a"]}, k, by_url=False))


class CrossSectionAndSiteDataTests(unittest.TestCase):
    def test_same_url_in_another_section_is_a_duplicate_but_a_similar_title_is_not(self):
        ext = {"name": "Glarity", "source_urls": ["https://github.com/a/glarity"], "store_url": f"https://chromewebstore.google.com/detail/{ID}"}
        known = dedupe.known_from_entries([ext], "an entry in extensions", url_only=True)
        skill = {"name": "Glarity", "source_urls": ["https://github.com/A/Glarity"]}
        self.assertIn("same URL", dedupe.find_duplicate(skill, known))
        self.assertIsNone(dedupe.find_duplicate({"name": "Glarity", "source_urls": ["https://github.com/other/thing"]}, known))

    def test_data_already_delivered_to_the_site_is_known(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "wrangler.jsonc").write_text("{}")
            sec = Path(d) / "public" / "data" / "prompts"
            sec.mkdir(parents=True)
            (sec / "p-123456.json").write_text(json.dumps({"id": "p-123456", "title": "Draft a client proposal", "prompt": "You are a freelancer who writes short proposals for [JOB]", "source_urls": ["https://docs.example.com/p"]}))
            (sec / "index.json").write_text("{}")
            k = site_known.load(d)["prompts"]
            self.assertEqual([x["title"] for x in k], ["Draft a client proposal"])
            e = {"title": "Draft a client proposal now", "prompt": "Write a proposal.", "source_urls": ["https://docs.example.com/q"]}
            self.assertTrue(dedupe.find_duplicate(e, k, by_url=False))


if __name__ == "__main__":
    unittest.main()


class SharedWordsAreNotEnoughForExtensionsTests(unittest.TestCase):
    def test_two_different_extensions_with_overlapping_generic_words_are_both_kept(self):
        # real case: "Glarity - Summary for Google/YouTube with ChatGPT" and "YouTube Summary with ChatGPT" are different extensions
        a = {"name": "Glarity - Summary for Google/YouTube with ChatGPT", "source_urls": ["https://github.com/a/glarity"], "store_url": f"https://chromewebstore.google.com/detail/glarity/{ID}"}
        other = "nmmicjeknamkfloonkhhcjmomieiodli"
        b = {"name": "YouTube Summary with ChatGPT", "source_urls": ["https://github.com/b/ytsummary"], "store_url": f"https://chromewebstore.google.com/detail/yt/{other}"}
        self.assertIsNone(dedupe.find_duplicate(b, dedupe.known_from_entries([a])))
        same_id = dict(b, store_url=f"https://chromewebstore.google.com/detail/renamed/{ID}")
        self.assertIn("same URL", dedupe.find_duplicate(same_id, dedupe.known_from_entries([a])))
