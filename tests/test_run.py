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
        per_run = settings()["per_run_max"]["money"]
        self.assertEqual(run.cap_room("money", []), min(daily, per_run))  # one run adds at most per_run_max, so output is spread over the day
        with mock.patch.dict(settings()["per_run_max"], {"money": 99}):
            self.assertEqual(run.cap_room("money", []), daily)
        self.assertEqual(run.cap_room("money", [entry(i) for i in range(daily)]), 0)
        self.assertEqual(run.cap_room("money", [], limit=1), 1)
        weekly = settings()["caps"]["weekly"]["money"]
        spread = [entry(i, first_seen="2000-01-01") for i in range(weekly)]  # old entries do not count
        self.assertEqual(run.cap_room("money", spread), min(daily, per_run))

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
        known = [{"title": "", "urls": {run.canon_key("https://b.com/2")}, "where": "site"}]
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


class RunLogTests(unittest.TestCase):
    def test_a_model_outage_is_reported_not_fatal(self):
        from xplorekit import llm
        cands = [{"title": "x", "url": "https://x.com/a", "snippet": "skill claude", "source_id": "s"}]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(run, "CACHE", Path(d) / "cache"), mock.patch("xplorekit.llm.available", lambda: True), \
                mock.patch.object(run, "collect_section", lambda s, log: (cands, [("s", "ok", 1)])), mock.patch.object(run.enrich, "enrich", lambda c, s: c), \
                mock.patch.object(run.agents.AGENTS["skills"], "run", side_effect=llm.LLMError("claude CLI failed on every token: slot 1: exit 1")):
            args = run.argparse.Namespace(out=d, site_dir=None, drafts_file=None, verdicts_file=None, limit=None, use_cache=False, collect_only=False)
            rep = {}
            self.assertEqual(run.process_section("skills", args, log=lambda *_: None, rep=rep), (0, 0))
        self.assertEqual(rep["status"], "agent_failed")
        self.assertEqual(rep["sources"], [{"id": "s", "status": "ok", "count": 1}])

    def test_runs_are_appended_and_trimmed(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(5):
                run.append_run(Path(d), {"n": i}, keep=3)
            self.assertEqual([r["n"] for r in json.loads((Path(d) / "runs.json").read_text())], [2, 3, 4])

    def test_collected_count_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "d.json"
            f.write_text(json.dumps([h.DRAFTS["skills"]]))
            with mock.patch.object(run, "CACHE", Path(d) / "c"), mock.patch.object(editor, "default_fetch_text", lambda u: h.SOURCE_TEXT["skills"]), \
                    mock.patch("xplorekit.verify.links.check", lambda u: ("ok", 200)), mock.patch.object(run, "settings", run.settings):
                args = run.argparse.Namespace(out=d, site_dir=None, drafts_file=None, verdicts_file=None, limit=None, use_cache=True, collect_only=False)
                (Path(d) / "c").mkdir()
                (Path(d) / "c" / "skills.json").write_text("[]")
                rep = {}
                run.process_section("skills", args, log=lambda *_: None, rep=rep)
                self.assertEqual(rep["collected"], 0)
