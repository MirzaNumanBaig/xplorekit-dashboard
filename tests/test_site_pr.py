import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from xplorekit import site_pr

_OPEN = []
PAGE = "public/prompts/index.html"
OLD = "<main>\n<p>hand written</p>\n</main>"
WITH_BLOCK = "<main>\n<p>hand written</p>\n<!-- feed:prompts:start -->\n<div>cards</div>\n<!-- feed:prompts:end -->\n</main>"


def site_with(page_text):
    d = tempfile.TemporaryDirectory()
    _OPEN.append(d)
    p = Path(d.name) / PAGE
    p.parent.mkdir(parents=True)
    p.write_text(page_text)
    return d


class CheckTests(unittest.TestCase):
    def tearDown(self):
        while _OPEN:
            _OPEN.pop().cleanup()

    def test_only_data_and_the_four_hub_pages_may_change(self):
        self.assertIsNone(site_pr.check_paths(["public/data/skills/x.json", "public/prompts/index.html", "public/extensions-directory/index.html"]))
        self.assertIn("unexpected", site_pr.check_paths(["public/data/a.json", "public/css/styles.css"]))
        self.assertIn("unexpected", site_pr.check_paths(["CLAUDE.md"]))
        self.assertIn("unexpected", site_pr.check_paths(["public/index.html"]))

    def test_size_limit(self):
        self.assertIsNone(site_pr.check_size(["f"] * 10))
        self.assertIn("limit", site_pr.check_size(["f"] * 500))

    def test_hub_pages_may_change_only_inside_the_feed_block(self):
        d = site_with(WITH_BLOCK.replace("cards", "NEW cards"))
        with mock.patch.object(site_pr, "git", lambda *a, **k: WITH_BLOCK):
            self.assertIsNone(site_pr.check_pages_outside_blocks(d.name, [PAGE]))  # only the block changed
        d2 = site_with(WITH_BLOCK.replace("hand written", "hand written, edited"))
        with mock.patch.object(site_pr, "git", lambda *a, **k: WITH_BLOCK):
            self.assertIn("outside the generated feed block", site_pr.check_pages_outside_blocks(d2.name, [PAGE]))
        d3 = site_with(WITH_BLOCK)
        with mock.patch.object(site_pr, "git", lambda *a, **k: OLD):  # first insertion of the block into a page that had none
            self.assertIsNone(site_pr.check_pages_outside_blocks(d3.name, [PAGE]))

    def test_entries_need_a_fact_check_and_no_counts(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "public/data/skills"
            f.mkdir(parents=True)
            rel = "public/data/skills/a.json"
            (f / "a.json").write_text(json.dumps({"verified": ["schema", "fact_check:llm"], "name": "A"}))
            self.assertIsNone(site_pr.check_data(d, [rel]))
            (f / "a.json").write_text(json.dumps({"verified": ["schema", "rules_only"]}))
            self.assertIn("no fact-check", site_pr.check_data(d, [rel]))
            (f / "a.json").write_text(json.dumps({"verified": ["fact_check:llm"], "stars": 5000}))
            self.assertIn("popularity-count", site_pr.check_data(d, [rel]))
            (f / "a.json").write_text("{not json")
            self.assertIn("not valid JSON", site_pr.check_data(d, [rel]))


class DeliverTests(unittest.TestCase):
    """The decision to publish: merge only when auto-merge is on AND every check passed."""

    def run_deliver(self, files, checks_fail=None, auto=True, mode=None):
        calls = []
        def fake_git(site, *args, **k):
            return "\n".join(f if "\t" in f else "M\t" + f for f in files) if args[:2] == ("diff", "--cached") else ""
        def fake_api(method, path, body=None):
            calls.append((method, path))
            if method == "GET":
                return 200, []
            if method == "POST":
                return 201, {"number": 77}
            if method == "PUT":
                return 200, {"merged": True}
            return 200, {}
        results = [("a check", checks_fail)]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(site_pr, "git", fake_git), mock.patch.object(site_pr, "git_ok", lambda *a: True), mock.patch.object(site_pr, "api", fake_api), \
                mock.patch.object(site_pr, "run_checks", lambda s, f: results), mock.patch.object(site_pr.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 0, "", "")), \
                mock.patch.dict(site_pr.settings(), {"publish_mode": mode or ("publish" if auto else "pending")}):
            body = Path(d) / "pr.md"
            body.write_text("Automated.")
            return site_pr.deliver(d, body, "owner/site"), calls

    def test_everything_passes_and_auto_merge_is_on_publishes_and_cleans_up(self):
        out, calls = self.run_deliver(["public/data/skills/a.json"])
        self.assertEqual((out["state"], out["pr"]), ("merged", 77))
        self.assertIn(("PUT", "/repos/owner/site/pulls/77/merge"), calls)
        self.assertEqual(calls[-1][0], "DELETE")

    def test_a_failed_check_leaves_the_pr_open_for_a_human_and_never_merges(self):
        out, calls = self.run_deliver(["public/data/skills/a.json"], checks_fail="a hub page changed outside the block")
        self.assertEqual(out["state"], "open_for_review")
        self.assertIn("outside the block", out["reason"])
        self.assertFalse([c for c in calls if c[0] == "PUT"])

    def test_the_kill_switch_stops_merging_but_still_opens_the_pr(self):
        out, calls = self.run_deliver(["public/data/skills/a.json"], auto=False)
        self.assertEqual(out["state"], "open_for_review")
        self.assertIn("pending", out["reason"])
        self.assertFalse([c for c in calls if c[0] == "PUT"])
        self.assertTrue([c for c in calls if c[0] == "POST"])

    def test_nothing_new_does_nothing(self):
        out, calls = self.run_deliver([])
        self.assertEqual(out["state"], "nothing_new")
        self.assertEqual(calls, [])

    def test_an_existing_open_pr_is_updated_not_duplicated(self):
        def fake_api(method, path, body=None):
            return (200, [{"number": 5}]) if method == "GET" else (200, {"merged": True})
        with tempfile.TemporaryDirectory() as d, mock.patch.object(site_pr, "git", lambda s, *a, **k: "M\tpublic/data/x.json" if a[:2] == ("diff", "--cached") else ""), \
                mock.patch.object(site_pr, "git_ok", lambda *a: True), mock.patch.object(site_pr, "api", fake_api), mock.patch.object(site_pr, "run_checks", lambda s, f: [("c", None)]), \
                mock.patch.object(site_pr.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 0, "", "")):
            out = site_pr.deliver(d, Path(d) / "missing.md", "o/s")
        self.assertEqual(out["pr"], 5)


if __name__ == "__main__":
    unittest.main()


class PublishedRecordTests(unittest.TestCase):
    def test_a_merged_delivery_is_recorded_with_date_and_pr_and_withdrawals_are_marked(self):
        files = ["A\tpublic/data/skills/graphify-aaaaaa.json", "M\tpublic/data/skills/index.json", "D\tpublic/data/prompts/old-bbbbbb.json", "M\tpublic/prompts/index.html"]
        out, calls = DeliverTests().run_deliver(files)
        self.assertEqual(out["state"], "merged")
        self.assertEqual(out["delivered"], [{"section": "skills", "id": "graphify-aaaaaa"}])  # index files and pages are not entries
        self.assertEqual(out["withdrawn"], [{"section": "prompts", "id": "old-bbbbbb"}])
        with tempfile.TemporaryDirectory() as d:
            Path(d, "published.json").write_text(json.dumps({"old-bbbbbb": {"section": "prompts", "published_at": "2026-11-01", "pr": 70, "withdrawn_at": None}}))
            site_pr.record_published(d, {**out, "date": "2026-11-17", "pr": 80})
            book = json.loads(Path(d, "published.json").read_text())
            self.assertEqual(book["graphify-aaaaaa"], {"section": "skills", "published_at": "2026-11-17", "pr": 80, "withdrawn_at": None})
            self.assertEqual(book["old-bbbbbb"]["withdrawn_at"], "2026-11-17")
            self.assertEqual(book["old-bbbbbb"]["published_at"], "2026-11-01")  # the original date is kept
            site_pr.record_published(d, {**out, "date": "2026-11-18", "pr": 81})  # delivered again later: date and PR are not rewritten
            self.assertEqual(json.loads(Path(d, "published.json").read_text())["graphify-aaaaaa"]["published_at"], "2026-11-17")

    def test_a_pr_left_open_for_a_human_records_nothing_as_published(self):
        out, _ = DeliverTests().run_deliver(["A\tpublic/data/skills/x-111111.json"], checks_fail="a check failed")
        with tempfile.TemporaryDirectory() as d:
            site_pr.record_published(d, {**out, "date": "2026-11-17"})
            self.assertFalse(Path(d, "published.json").exists())


class PublishModeTests(unittest.TestCase):
    def test_draft_mode_touches_nothing_and_says_so(self):
        out, calls = DeliverTests().run_deliver(["A\tpublic/data/skills/a.json"], mode="draft")
        self.assertEqual(out["state"], "held_as_draft")
        self.assertEqual(calls, [])  # no pull request, no merge, no API call at all

    def test_pending_mode_opens_the_pr_but_never_merges_and_publish_mode_merges(self):
        out, calls = DeliverTests().run_deliver(["A\tpublic/data/skills/a.json"], mode="pending")
        self.assertEqual(out["state"], "open_for_review")
        self.assertFalse([c for c in calls if c[0] == "PUT"])
        self.assertTrue([c for c in calls if c[0] == "POST"])
        out, calls = DeliverTests().run_deliver(["A\tpublic/data/skills/a.json"], mode="publish")
        self.assertEqual(out["state"], "merged")

    def test_the_old_auto_merge_setting_still_means_the_same_thing(self):
        from xplorekit import common
        with mock.patch.dict(common.settings(), {"auto_merge_site": False}, clear=False):
            s = common.settings()
            s.pop("publish_mode", None)
            self.assertEqual(common.publish_mode(), "pending")
        with mock.patch.dict(common.settings(), {"publish_mode": "draft"}):
            self.assertEqual(common.publish_mode(), "draft")
        with mock.patch.dict(common.settings(), {"publish_mode": "nonsense"}):
            self.assertEqual(common.publish_mode(), "pending")  # a typo must never publish live: it falls back to the safe side
        with mock.patch.dict(common.settings(), {"auto_merge_site": True}):
            common.settings().pop("publish_mode", None)
            self.assertEqual(common.publish_mode(), "publish")


class ResearchPagePathTests(unittest.TestCase):
    def test_entry_pages_and_sitemap_are_allowed_but_other_files_are_not(self):
        from xplorekit import site_pr
        ok = ["public/data/prompts/a.json", "public/research/prompts/a.html", "public/sitemap.xml", "public/prompts/index.html"]
        self.assertIsNone(site_pr.check_paths(ok))
        self.assertIn("unexpected", site_pr.check_paths(ok + ["public/index.html"]))
        self.assertIn("unexpected", site_pr.check_paths(["public/robots.txt"]))
