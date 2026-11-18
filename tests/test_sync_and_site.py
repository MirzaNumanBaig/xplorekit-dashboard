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
            self.assertEqual(k["skills"][0]["urls"], {"github:anthropics/skills"})
            self.assertEqual([x["title"] for x in k["money"]], ["Get paid to train AI"])  # hub index.html is skipped
            self.assertEqual(sorted(x["title"] for x in k["extensions"]), ["Bar Tool", "Foo Tool"])
            self.assertEqual(len(k["extensions"]), 2)

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
        self.assertIn("merges itself", body)


if __name__ == "__main__":
    unittest.main()


class OnlyFactCheckedEntriesShipTests(unittest.TestCase):
    def test_entries_without_a_fact_check_never_reach_the_site_and_the_index_matches(self):
        with tempfile.TemporaryDirectory() as t:
            data, site = Path(t) / "data", Path(t) / "site"
            fake_site(site)
            (data / "skills").mkdir(parents=True)
            good = {"id": "good-111111", "name": "Good", "source_url": "https://x.com/g", "quality_score": 85, "verified": ["schema", "fact_check:llm"]}
            weak = {"id": "weak-222222", "name": "Weak", "source_url": "https://x.com/w", "quality_score": 75, "verified": ["schema", "rules_only"]}
            for e in (good, weak):
                (data / "skills" / f"{e['id']}.json").write_text(json.dumps(e))
            (data / "skills" / "index.json").write_text(json.dumps({"section": "skills", "items": [{"id": "good-111111"}, {"id": "weak-222222"}]}))
            added, _, _ = sync_site.sync(data, site)
            out = site / "public" / "data" / "skills"
            self.assertTrue((out / "good-111111.json").exists())
            self.assertFalse((out / "weak-222222.json").exists())
            self.assertEqual([i["id"] for i in json.loads((out / "index.json").read_text())["items"]], ["good-111111"])
            (data / "skills" / "good-111111.json").write_text(json.dumps({**good, "verified": ["schema", "rules_only"]}))  # later loses its fact-check
            _, _, removed = sync_site.sync(data, site)
            self.assertEqual(removed, ["skills/good-111111.json"])  # and is withdrawn from the site


class ReverifyTests(unittest.TestCase):
    def test_a_rules_only_entry_is_upgraded_or_removed(self):
        from unittest import mock
        import tests.helpers as h
        from xplorekit import run
        from xplorekit.agents import editor_verifier as ed
        with tempfile.TemporaryDirectory() as d:
            e = ed.finalize("skills", h.DRAFTS["skills"])
            e.update({"quality_score": 79, "verified": ["schema", "rules_only"], "first_seen": "2026-01-02"})
            (Path(d) / "skills").mkdir()
            (Path(d) / "skills" / f"{e['id']}.json").write_text(json.dumps(e))
            args = run.argparse.Namespace(out=d, site_dir=None, verdicts_file=None)
            def run_with(verdict):
                with mock.patch.object(run, "make_fact_checker", lambda f: (lambda s, en, t: verdict, "llm")), mock.patch.object(ed, "default_fetch_text", lambda u: h.SOURCE_TEXT["skills"]), \
                        mock.patch("xplorekit.verify.links.check", lambda u: ("ok", 200)):
                    run.reverify(args, log=lambda *_: None)
            run_with({"supported": True, "score": 90, "issues": []})
            saved = run.load_entries(Path(d), "skills")[0]
            self.assertIn("fact_check:llm", saved["verified"])
            self.assertNotIn("rules_only", saved["verified"])
            self.assertEqual(saved["first_seen"], "2026-01-02")  # keeps its original date
            saved["verified"] = ["schema", "rules_only"]
            (Path(d) / "skills" / f"{saved['id']}.json").write_text(json.dumps(saved))
            run_with({"supported": False, "score": 20, "issues": ["invented install steps"]})
            self.assertEqual(run.load_entries(Path(d), "skills"), [])
            log = json.loads((Path(d) / "rejected" / "skills.json").read_text())
            self.assertEqual(log[-1]["reason"], "reverify_fact_check")


class ReverifyOrderTests(unittest.TestCase):
    def _setup(self, d, entries):
        from xplorekit import run
        (Path(d) / "prompts").mkdir()
        for e in entries:
            (Path(d) / "prompts" / f"{e['id']}.json").write_text(json.dumps(e))
        return run.argparse.Namespace(out=d, site_dir=None, verdicts_file=None)

    def _entries(self):
        import tests.helpers as h
        from xplorekit.agents import editor_verifier as ed
        a = ed.finalize("prompts", h.DRAFTS["prompts"])
        b = ed.finalize("prompts", {**h.DRAFTS["prompts"], "source_url": "https://example.com/other", "source_urls": ["https://example.com/other"]})
        b["id"] = "zz-" + b["id"]
        for i, e in enumerate((a, b)):
            e.update({"quality_score": 79, "verified": ["schema", "rules_only"], "first_seen": f"2026-01-0{i + 1}"})
        return a, b

    def _run(self, args, verdict):
        from unittest import mock
        import tests.helpers as h
        from xplorekit import run
        from xplorekit.agents import editor_verifier as ed
        def fact(s, en, t):
            if isinstance(verdict, Exception):
                raise verdict
            return verdict
        with mock.patch.object(run, "make_fact_checker", lambda f: (fact, "llm")), mock.patch.object(ed, "default_fetch_text", lambda u: h.SOURCE_TEXT["prompts"]), \
                mock.patch("xplorekit.verify.links.check", lambda u: ("ok", 200)):
            run.reverify(args, log=lambda *_: None)

    def test_two_duplicates_keep_exactly_one(self):
        from xplorekit import run
        with tempfile.TemporaryDirectory() as d:
            a, b = self._entries()
            args = self._setup(d, [a, b])
            self._run(args, {"supported": True, "score": 90, "issues": []})
            left = run.load_entries(Path(d), "prompts")
            self.assertEqual([e["id"] for e in left], [a["id"]])
            self.assertIn("fact_check:llm", left[0]["verified"])

    def test_an_ai_outage_leaves_entries_untouched(self):
        from xplorekit import run
        with tempfile.TemporaryDirectory() as d:
            a, b = self._entries()
            args = self._setup(d, [a, b])
            self._run(args, RuntimeError("model down"))
            left = run.load_entries(Path(d), "prompts")
            self.assertEqual([e["id"] for e in left], [a["id"]])  # the real duplicate goes; the first stays, unchecked, to retry
            self.assertIn("rules_only", left[0]["verified"])


class RelevantExcerptTests(unittest.TestCase):
    def test_a_claim_deep_in_a_long_page_is_included(self):
        from xplorekit.verify import rules
        filler = "General words about nothing in particular. " * 1200
        source = "Intro about the tool. " + filler + " Run npx magicinstall --global to install it. " + filler
        entry = {"summary": "Install with npx magicinstall --global", "install_steps": ["npx magicinstall --global"]}
        out = rules.relevant_excerpt(entry, source)
        self.assertLessEqual(len(out), 14000)
        self.assertIn("magicinstall", out)
        self.assertTrue(out.startswith("Intro about the tool."))
        self.assertEqual(rules.relevant_excerpt(entry, "short"), "short")


class RejectedRowTests(unittest.TestCase):
    def test_reasons_are_plain_english(self):
        from xplorekit import build_dashboard as bd
        self.assertIn("could not run", bd.reason_text("reverify_fact_check_failed"))
        self.assertIn("Already covered", bd.reason_text("duplicate"))
        self.assertEqual(bd.reason_text("something_new"), "something new")
