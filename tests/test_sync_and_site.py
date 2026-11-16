import json
import tempfile
import unittest
from pathlib import Path

from xplorekit import site_known, sync_site


def fake_site(root):
    pub = Path(root) / "public"
    (pub / "skills-directory" / "cat").mkdir(parents=True)
    (pub / "extensions-directory" / "cat").mkdir(parents=True)
    (pub / "make-money-with-ai").mkdir(parents=True)
    (Path(root) / "wrangler.jsonc").write_text("{}")
    (pub / "skills-directory" / "cat" / "mcp-builder.html").write_text(
        '<h1>mcp-builder</h1><a href="https://github.com/anthropics/skills">x</a><a href="https://fonts.googleapis.com/x">f</a><a href="https://www.linkedin.com/in/a">l</a>')
    (pub / "extensions-directory" / "cat" / "foo.html").write_text('<h1>Foo Tool</h1><a href="https://chromewebstore.google.com/detail/foo/abc">add</a>')
    (pub / "make-money-with-ai" / "index.html").write_text("<h1>Hub</h1>")
    (pub / "make-money-with-ai" / "plan.html").write_text("<h1>Get paid to train AI</h1>")
    (pub / "extensions-directory" / "index.json").write_text(json.dumps({"extensions": [{"name": "Bar Tool", "url": "/x"}]}))


class SiteKnownTests(unittest.TestCase):
    def test_reads_titles_and_outbound_urls_but_not_site_chrome(self):
        with tempfile.TemporaryDirectory() as d:
            fake_site(d)
            k = site_known.load(d)
            self.assertEqual([x["title"] for x in k["skills"]], ["mcp-builder"])
            self.assertEqual(k["skills"][0]["urls"], {"https://github.com/anthropics/skills"})
            self.assertEqual([x["title"] for x in k["money"]], ["Get paid to train AI"])  # hub index.html is skipped
            self.assertEqual(sorted(x["title"] for x in k["extensions"]), ["Bar Tool", "Foo Tool"])
            self.assertIn("https://chromewebstore.google.com/detail/foo/abc", k["extensions"][0]["urls"] | k["extensions"][1]["urls"])

    def test_empty_site_is_fine(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual({s: len(v) for s, v in site_known.load(d).items()}, {"extensions": 0, "skills": 0, "money": 0, "prompts": 0})


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data, self.site = Path(self.tmp.name) / "data", Path(self.tmp.name) / "site"
        fake_site(self.site)
        (self.data / "skills").mkdir(parents=True)
        (self.data / "rejected").mkdir()
        (self.data / "skills" / "a-123456.json").write_text(json.dumps({"id": "a-123456", "name": "A", "source_url": "https://x.com", "quality_score": 85, "verified": ["schema", "fact_check:llm"]}))
        (self.data / "skills" / "index.json").write_text("{}")
        (self.data / "rejected" / "skills.json").write_text("[]")

    def tearDown(self):
        self.tmp.cleanup()

    def test_copies_data_never_rejected_and_removes_stale_files(self):
        stale = self.site / "public" / "data" / "skills" / "gone.json"
        stale.parent.mkdir(parents=True)
        stale.write_text("{}")
        added, changed, removed = sync_site.sync(self.data, self.site)
        self.assertIn("skills/a-123456.json", added)
        self.assertEqual(removed, ["skills/gone.json"])
        self.assertFalse((self.site / "public" / "data" / "rejected").exists())
        self.assertTrue((self.site / "public" / "data" / "index.json").exists())
        self.assertEqual(sync_site.sync(self.data, self.site)[:2], ([], []))  # second run: nothing to do

    def test_refuses_the_wrong_repo(self):
        with tempfile.TemporaryDirectory() as other, self.assertRaises(SystemExit):
            sync_site.sync(self.data, other)

    def test_pr_body_lists_new_entries_with_source_and_checks(self):
        added, changed, removed = sync_site.sync(self.data, self.site)
        body = sync_site.pr_body(self.data, added, changed, removed)
        self.assertIn("**skills** · A · score 85", body)
        self.assertIn("source: https://x.com", body)
        self.assertIn("skim before merging", body)


if __name__ == "__main__":
    unittest.main()
