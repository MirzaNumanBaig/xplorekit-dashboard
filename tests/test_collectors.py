import json
import os
import unittest
from unittest import mock

from xplorekit import collectors
from xplorekit.collectors import github, hackernews, reddit, rss


class CollectorTests(unittest.TestCase):
    def test_rss_and_atom_parse(self):
        r = rss.parse('<rss><channel><item><title>T</title><link>https://a.com/1</link><description>&lt;p&gt;Hi &amp;amp; bye&lt;/p&gt;</description><pubDate>2026-11-02</pubDate></item></channel></rss>')
        self.assertEqual((r[0]["title"], r[0]["url"], r[0]["snippet"], r[0]["date"]), ("T", "https://a.com/1", "Hi & bye", "2026-11-02"))
        a = rss.parse('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>E</title><link href="https://a.com/e"/><updated>2026-11-03T10:00:00Z</updated></entry></feed>')
        self.assertEqual((a[0]["url"], a[0]["date"]), ("https://a.com/e", "2026-11-03"))

    def test_truncated_feed_keeps_complete_items(self):
        t = '<rss xmlns:c="x"><channel><item><title>A</title><link>https://a.com/1</link><c:encoded><![CDATA[x]]></c:encoded></item><item><title>B</title><link>https://a.com/2</link><description><![CDATA[cut'
        self.assertEqual([i["title"] for i in rss.parse(t)], ["A"])

    def test_hackernews_maps_hits(self):
        body = json.dumps({"hits": [{"objectID": "1", "title": "Show HN: tool", "url": "https://t.com", "points": 50, "num_comments": 3, "created_at": "2026-11-01T00:00:00Z"},
                                     {"objectID": "2", "title": "Ask HN", "url": None, "points": 40, "created_at": "2026-11-02T00:00:00Z"}]})
        with mock.patch.object(hackernews, "http_get", lambda url, *a, **k: (200, body)):
            out = hackernews.collect({"queries": ["q"], "min_points": 10})
        self.assertEqual(out[0]["url"], "https://t.com")
        self.assertEqual(out[1]["url"], "https://news.ycombinator.com/item?id=2")

    def test_github_skips_archived_and_forks(self):
        body = json.dumps({"items": [{"full_name": "a/ok", "html_url": "https://github.com/a/ok", "description": "d", "stargazers_count": 5, "pushed_at": "2026-11-01T00:00:00Z"},
                                      {"full_name": "a/old", "html_url": "https://github.com/a/old", "archived": True}, {"full_name": "a/fork", "html_url": "x", "fork": True}]})
        with mock.patch.object(github, "http_get", lambda url, *a, **k: (200, body)):
            self.assertEqual([c["title"] for c in github.collect({"queries": ["q"]})], ["a/ok"])

    def test_sources_needing_keys_are_skipped_not_fatal(self):
        src = {"id": "r", "type": "reddit", "requires_key": "REDDIT_CLIENT_ID,REDDIT_CLIENT_SECRET"}
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(collectors.missing_key(src), ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"])
        cfg = {"money": [src, {"id": "bad", "type": "rss", "url": "https://x"}, {"id": "off", "type": "rss", "enabled": False}]}
        with mock.patch.object(collectors, "sources", lambda: cfg), mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(rss, "http_get", side_effect=OSError("boom")):
            items, report = collectors.collect_section("money", log=lambda *_: None)
        self.assertEqual(items, [])
        self.assertTrue(report[0][1].startswith("skipped") and report[1][1].startswith("error") and report[2][1] == "disabled")

    def test_reddit_never_uses_the_html_site(self):
        import inspect
        self.assertNotIn(".rss", inspect.getsource(reddit))  # reddit.com's robots.txt disallows crawling: official API only

    def test_all_configured_source_types_have_a_collector(self):
        from xplorekit.common import sources
        reg = collectors.registry()
        for section, items in sources().items():
            for s in items if not section.startswith("_") else []:
                self.assertIn(s["type"], reg, s["id"])


if __name__ == "__main__":
    unittest.main()


class MoneySourcesTests(unittest.TestCase):
    def test_money_reads_earning_programme_pages_not_launch_feeds_or_news(self):
        import json
        from xplorekit.common import ROOT
        ids = {s["id"]: s for s in json.loads((ROOT / "xplorekit" / "config" / "sources.json").read_text())["money"]}
        for noisy in ("ph-feed", "rundown", "bens-bites"):
            self.assertNotIn(noisy, ids)  # product launches and news are not ways to earn
        urls = ids["earning-programs"]["urls"]
        self.assertGreaterEqual(len(urls), 8)
        self.assertTrue(any("youtube.com" in u or "support.google.com/youtube" in u for u in urls))
