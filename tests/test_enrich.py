import unittest
from unittest import mock

from xplorekit import enrich
from xplorekit.verify import dedupe


class EnrichTests(unittest.TestCase):
    def test_store_links_are_normalised_and_deduped(self):
        text = ("Install from https://chrome.google.com/webstore/detail/foo/abcdefghijklmnopabcdefghijklmnop?hl=en or "
                "https://chromewebstore.google.com/detail/foo/abcdefghijklmnopabcdefghijklmnop and http://chromewebstore.google.com/detail/bar")
        self.assertEqual(enrich.store_links(text), ["https://chromewebstore.google.com/detail/foo/abcdefghijklmnopabcdefghijklmnop", "https://chromewebstore.google.com/detail/bar"])

    def test_relevance_filter(self):
        self.assertTrue(enrich.relevant({"title": "How I earn $400 a month freelancing with Claude", "url": "https://a.com"}, "money"))
        self.assertFalse(enrich.relevant({"title": "Open source TTS that speaks Southern American", "snippet": "text to speech", "url": "https://hf.co/x"}, "money"))

    def test_github_candidates_get_readme_details_and_store_links(self):
        c = [{"url": "https://github.com/a/b", "title": "a/b"}, {"url": "https://example.com/x", "title": "x"}]
        readme = "# b\n![badge](x.png)\nGet it at https://chromewebstore.google.com/detail/b/abcdefghijklmnopabcdefghijklmnop\nSome <b>text</b>."
        with mock.patch.object(enrich, "http_get", lambda url, **k: (200, readme)):
            enrich.enrich(c, "extensions")
        self.assertEqual(c[0]["store_urls"], ["https://chromewebstore.google.com/detail/b/abcdefghijklmnopabcdefghijklmnop"])
        self.assertNotIn("badge", c[0]["details"])
        self.assertNotIn("details", c[1])

    def test_enrichment_is_limited_and_survives_network_errors(self):
        c = [{"url": f"https://github.com/a/r{i}", "title": "t"} for i in range(5)]
        calls = []
        def fake(url, **k):
            calls.append(url)
            raise OSError("down")
        with mock.patch.object(enrich, "http_get", fake):
            enrich.enrich(c, "skills", limit=2)
        self.assertEqual(len(calls), 2)

    def test_prompts_may_share_a_source_url(self):
        from xplorekit.common import canon_key
        k = [{"title": "Other prompt", "urls": {canon_key("https://docs.example.com/p")}, "where": "accepted entry"}]
        e = {"title": "A different prompt", "source_urls": ["https://docs.example.com/p"]}
        self.assertIsNone(dedupe.find_duplicate(e, k, by_url=False))
        self.assertTrue(dedupe.find_duplicate(e, k, by_url=True))


if __name__ == "__main__":
    unittest.main()


class GithubLinkTests(unittest.TestCase):
    def test_github_repo_urls_are_recognised(self):
        self.assertEqual(enrich.github_repo("https://github.com/a/b"), ("a", "b"))
        self.assertEqual(enrich.github_repo("https://github.com/a/b/blob/main/x/SKILL.md?plain=1"), ("a", "b"))
        self.assertEqual(enrich.github_repo("https://github.com/a/b.git"), ("a", "b"))
        self.assertIsNone(enrich.github_repo("https://github.com/topics/claude"))
        self.assertIsNone(enrich.github_repo("https://example.com/a/b"))

    def test_link_check_uses_the_raw_host_for_github(self):
        from xplorekit.verify import links
        seen = []
        def fake(url, **k):
            seen.append(url)
            return (200, "") if url.endswith("/README.md") and "/real/" in url else (404, "")
        with mock.patch.object(links, "http_get", fake):
            self.assertEqual(links.check("https://github.com/real/repo"), ("ok", 200))
            self.assertEqual(links.check("https://github.com/ghost/repo"), ("dead", 404))
        self.assertTrue(all(u.startswith("https://raw.githubusercontent.com/") for u in seen))


class HeadFallbackTests(unittest.TestCase):
    def test_head_404_but_get_200_is_alive(self):
        from xplorekit.verify import links
        calls = []
        def fake(url, method=None, **k):
            calls.append(method or "GET")
            return (404, "") if method == "HEAD" else (200, "page")
        with mock.patch.object(links, "robots_allowed", lambda u: True), mock.patch.object(links, "http_get", fake):
            self.assertEqual(links.check("https://example.com/page"), ("ok", 200))
        self.assertEqual(calls, ["HEAD", "GET"])

    def test_dead_only_when_get_also_fails(self):
        from xplorekit.verify import links
        with mock.patch.object(links, "robots_allowed", lambda u: True), mock.patch.object(links, "http_get", lambda url, **k: (404, "")):
            self.assertEqual(links.check("https://example.com/gone"), ("dead", 404))


class FocusExcerptTests(unittest.TestCase):
    def test_the_relevant_rules_are_picked_over_navigation_boilerplate(self):
        nav = "Help Topics Sign in Give Feedback Bookshelf Reports Community Marketing Account and Taxes Bank account " * 40
        rules = ("Artificial intelligence (AI) content. We require you to inform us of AI-generated content when you publish a book. "
                 "You are not required to disclose AI-assisted content. Content that is freely available on the web is not accepted. ")
        page = nav + rules + nav
        out = enrich.focus_excerpt(page, size=1200)
        self.assertIn("AI-generated content", out)
        self.assertIn("not required to disclose AI-assisted", out)
        self.assertLessEqual(len(out), 1200)

    def test_short_pages_pass_through_unchanged_and_candidates_get_details(self):
        self.assertEqual(enrich.focus_excerpt("short page text"), "short page text")
        c = [{"url": "https://help.example.com/x", "title": "x", "full": "intro " * 3000 + " We require you to disclose AI-generated content. " + "outro " * 3000, "kind": "page"}]
        enrich.enrich(c, "money")
        self.assertIn("disclose AI-generated content", c[0]["details"])

    def test_slices_join_without_splitting_words_and_gaps_are_marked(self):
        text = ("x" * 380) + ("You are not required to disclose AI-assisted content. " * 8) + ("y" * 3000) + ("An AI-generated cover must be disclosed. " * 8) + ("z" * 3000)
        out = enrich.focus_excerpt(text, size=2000)
        self.assertIn("not required to disclose AI-assisted content.", out)
        self.assertIn("An AI-generated cover must be disclosed.", out)
        self.assertIn(" … ", out)  # the two separate passages are marked as separate
