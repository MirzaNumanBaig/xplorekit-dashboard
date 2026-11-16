import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tests.helpers as h
from xplorekit import run
from xplorekit.common import settings, today
from xplorekit.agents import editor_verifier as editor


def entry(i, first_seen=None):
    return {"id": f"e{i}", "first_seen": first_seen or today(), "source_url": f"https://example.com/{i}", "source_urls": [f"https://example.com/{i}"], "title": f"t{i}", "quality_score": 80,
            "last_checked": today(), "status": "active"}


class RunTests(unittest.TestCase):
    def test_daily_and_weekly_caps(self):
        daily = settings()["caps"]["daily"]["money"]
        self.assertEqual(run.cap_room("money", []), daily)
        self.assertEqual(run.cap_room("money", [entry(i) for i in range(daily)]), 0)
        self.assertEqual(run.cap_room("money", [], limit=1), 1)
        weekly = settings()["caps"]["weekly"]["money"]
        spread = [entry(i, first_seen="2000-01-01") for i in range(weekly)]  # old entries do not count
        self.assertEqual(run.cap_room("money", spread), daily)

    def test_weekly_cap_blocks_even_when_daily_is_free(self):
        from datetime import date, timedelta
        weekly = settings()["caps"]["weekly"]["money"]
        recent = (date.fromisoformat(today()) - timedelta(days=3)).isoformat()
        self.assertEqual(run.cap_room("money", [entry(i, recent) for i in range(weekly)]), 0)

    def test_diversify_interleaves_sources(self):
        c = [{"source_id": "gh", "score": 9000 - i, "url": f"g{i}"} for i in range(5)] + [{"source_id": "hn", "score": 5, "url": "h0"}, {"source_id": "hn", "score": 3, "url": "h1"}]
        order = [x["url"] for x in run.diversify(c)]
        self.assertEqual(order[:4], ["g0", "h0", "g1", "h1"])

    def test_prefilter_drops_known_rejected_and_repeats(self):
        cands = [{"url": "https://a.com/1"}, {"url": "https://www.a.com/1/?utm_source=x"}, {"url": "https://b.com/2"}, {"url": "https://c.com/3"}, {"url": "ftp://d"}]
        known = [{"title": "", "urls": {"https://b.com/2"}, "where": "site"}]
        rejected = [{"url": "https://c.com/3", "date": today()}]
        out = run.prefilter(cands, "money", [], known, rejected)
        self.assertEqual([c["url"] for c in out], ["https://a.com/1"])

    def test_old_rejections_are_retried(self):
        out = run.prefilter([{"url": "https://c.com/3"}], "money", [], [], [{"url": "https://c.com/3", "date": "2020-01-01"}])
        self.assertEqual(len(out), 1)

    def test_save_writes_entries_index_and_rejected_log(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            acc, rej = editor.review("skills", [h.DRAFTS["skills"], {"title": "bad"}], h.ctx("skills", fact=h.good_verdict))
            run.save(root, "skills", acc, rej)
            index = json.loads((root / "skills" / "index.json").read_text())
            self.assertEqual(len(index["items"]), 1)
            self.assertNotIn("stars", json.dumps(index).lower())
            self.assertEqual(json.loads((root / "rejected" / "skills.json").read_text())[0]["reason"], "schema")
            self.assertEqual(len(run.load_entries(root, "skills")), 1)

    def test_drafts_file_runs_only_the_editor(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "drafts.json"
            f.write_text(json.dumps([h.DRAFTS["skills"]]))
            v = Path(d) / "verdicts.json"
            v.write_text(json.dumps({"https://github.com/example/example-skill": {"supported": True, "score": 88, "issues": []}}))
            args = run.argparse.Namespace(out=d, site_dir=None, drafts_file=str(f), verdicts_file=str(v), limit=None, use_cache=False, collect_only=False)
            with mock.patch.object(run, "CACHE", Path(d) / "cache"), mock.patch.object(editor, "default_fetch_text", lambda u: h.SOURCE_TEXT["skills"]), mock.patch("xplorekit.verify.links.check", lambda u: ("ok", 200)):
                a, r = run.process_section("skills", args, log=lambda *_: None)
            self.assertEqual((a, r), (1, 0))
            saved = run.load_entries(Path(d), "skills")[0]
            self.assertIn("fact_check:manual", saved["verified"])
            self.assertLessEqual(saved["quality_score"], 88, "a reviewer can only lower the rule score, never raise it")

    def test_agent_is_skipped_cleanly_without_a_model(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(run, "CACHE", Path(d) / "cache"), mock.patch("xplorekit.llm.available", lambda: False), mock.patch.object(run, "collect_section", lambda s, log: ([{"title": "x", "url": "https://x.com/a", "snippet": "", "source_id": "s"}], [])):
            args = run.argparse.Namespace(out=d, site_dir=None, drafts_file=None, verdicts_file=None, limit=None, use_cache=False, collect_only=False)
            logs = []
            self.assertEqual(run.process_section("skills", args, log=logs.append), (0, 0))
            self.assertTrue(any("agent skipped" in l for l in logs))


if __name__ == "__main__":
    unittest.main()
