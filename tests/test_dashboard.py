import json
import re
import tempfile
import unittest
from pathlib import Path

import tests.helpers as h
from xplorekit import build_dashboard as bd
from xplorekit.agents import editor_verifier as editor
from xplorekit.common import today


def write_entry(root, section, **over):
    e = editor.finalize(section, h.DRAFTS[section])
    e.update({"quality_score": 88, "verified": ["schema", "fact_check:llm"], **over})
    d = Path(root) / section
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{e['id']}.json").write_text(json.dumps(e))
    return e


def research_run(**kw):
    return {"type": "research", "date": today(), "time": today() + "T05:00:00+00:00", "provider": "claude_cli", "dry_run": False,
            "llm": {"calls": 4, "failures": 0, "token_slots_used": [1]}, "sections": {"money": {"status": "ok", "accepted": 1, "rejected": 0}}, **kw}


class DatasetTests(unittest.TestCase):
    def test_empty_data_dir_still_builds_and_asks_for_a_first_run(self):
        with tempfile.TemporaryDirectory() as d:
            ds = bd.build_dataset(d)
            self.assertEqual([s["stats"]["total"] for s in ds["sections"]], [0, 0, 0, 0])
            self.assertEqual(ds["health"][0]["level"], "warn")
            self.assertIn("No research run", ds["health"][0]["text"])
            self.assertIn("<title>Xplorekit Research Dashboard</title>", bd.render(ds))

    def test_counts_caps_reasons_and_rules_only(self):
        with tempfile.TemporaryDirectory() as d:
            write_entry(d, "money")
            write_entry(d, "skills", first_seen="2000-01-01", status="stale", verified=["schema", "rules_only"])
            Path(d, "rejected").mkdir()
            Path(d, "rejected", "money.json").write_text(json.dumps([{"reason": "money_gate", "date": today(), "title": "t", "url": "https://x.com", "detail": "d"},
                                                                     {"reason": "duplicate", "date": "2000-01-01", "title": "old", "url": "", "detail": ""}]))
            ds = bd.build_dataset(d)
            money = ds["sections"][0]
            self.assertEqual((money["stats"]["total"], money["stats"]["today"], money["stats"]["week"]), (1, 1, 1))
            self.assertEqual(money["stats"]["reasons_week"], {"money_gate": 1})  # the 2000-01-01 rejection is outside the week
            self.assertEqual(money["caps"], {"daily": 3, "weekly": 15})
            skills = [s for s in ds["sections"] if s["key"] == "skills"][0]
            self.assertEqual((skills["stats"]["stale"], skills["stats"]["rules_only"], skills["stats"]["week"]), (1, 1, 0))
            self.assertEqual(len(ds["rejected"]), 2)
            self.assertEqual(ds["rejected"][0]["reason"], "money_gate")  # newest first

    def test_rows_carry_section_specific_detail(self):
        with tempfile.TemporaryDirectory() as d:
            write_entry(d, "money"); write_entry(d, "extensions"); write_entry(d, "prompts"); write_entry(d, "skills")
            by = {s["key"]: s["entries"][0] for s in bd.build_dataset(d)["sections"]}
            self.assertIn("15-25 USD/hour (per source)", by["money"]["detail"])
            self.assertIn("freemium", by["extensions"]["detail"])
            self.assertTrue(by["extensions"]["link2"].startswith("https://chromewebstore.google.com/"))
            self.assertIn("business", by["prompts"]["detail"])
            self.assertEqual(by["skills"]["link2"], "https://github.com/example/example-skill")

    def test_sources_show_last_run_status(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "runs.json").write_text(json.dumps([research_run(sections={"money": {"status": "ok", "accepted": 0, "rejected": 0, "sources": [{"id": "hn-money", "status": "ok", "count": 7}]}})]))
            src = {(s["section"], s["id"]): s for s in bd.build_dataset(d)["sources"]}
            self.assertEqual(src[("money", "hn-money")]["last_count"], 7)
            self.assertIsNone(src[("money", "gh-money")]["last_status"])
            self.assertTrue(src[("money", "reddit-sideproject")]["requires_key"])


class HealthTests(unittest.TestCase):
    def levels(self, runs):
        return [x["level"] for x in bd.health(runs, [], today())]

    def test_ok_when_the_last_run_is_fresh_and_clean(self):
        self.assertEqual(self.levels([research_run()]), ["ok"])

    def test_old_run_no_model_and_failed_agent_are_problems(self):
        self.assertEqual(self.levels([research_run(date="2000-01-01")]), ["bad"])
        self.assertEqual(self.levels([research_run(provider="none")]), ["bad"])
        self.assertEqual(self.levels([research_run(sections={"skills": {"status": "agent_failed"}})]), ["bad"])

    def test_token_failures_are_a_warning_naming_the_slot(self):
        out = bd.health([research_run(llm={"calls": 3, "failures": 1, "token_slots_used": [2]})], [], today())
        self.assertEqual(out[0]["level"], "warn")
        self.assertIn("slot(s) used: 2", out[0]["text"])

    def test_dry_runs_do_not_count_as_real_runs(self):
        self.assertEqual(self.levels([research_run(dry_run=True)]), ["warn"])


class SafetyTests(unittest.TestCase):
    def test_hostile_text_cannot_break_out_of_the_data_script(self):
        with tempfile.TemporaryDirectory() as d:
            write_entry(d, "skills", name="</script><script>window.pwned=1</script>")
            html = bd.render(bd.build_dataset(d))
        script_blocks = re.findall(r"<script[^>]*>", html)
        self.assertEqual(len(script_blocks), 2)  # the data block and the app: nothing injected
        data = re.search(r'<script id="data"[^>]*>(.*?)</script>', html, re.S).group(1)
        self.assertNotIn("<", data)
        self.assertIn("</script><script>window.pwned=1</script>", json.loads(data)["sections"][3]["entries"][0]["title"])  # decoded intact in the browser

    def test_page_loads_nothing_from_the_network(self):
        t = bd.TEMPLATE.read_text("utf-8")
        self.assertNotRegex(t, r'<script[^>]+src=')
        self.assertNotRegex(t, r'<link[^>]+href="https?:')
        self.assertNotIn("fetch(", t)
        self.assertNotIn("innerHTML", t)  # all dynamic text goes through textContent


if __name__ == "__main__":
    unittest.main()


class PauseTests(unittest.TestCase):
    def test_pause_is_shown_and_stops_a_real_run(self):
        from unittest import mock
        from xplorekit import run
        real = dict(bd.settings())
        with mock.patch.object(bd, "settings", lambda: {**real, "paused": True}), mock.patch.object(run, "settings", lambda: {**real, "paused": True}):
            self.assertEqual(bd.health([research_run()], [], today())[0]["level"], "warn")
            self.assertIn("paused", bd.health([research_run()], [], today())[0]["text"])
            with tempfile.TemporaryDirectory() as d:
                self.assertEqual(run.main(["--section", "skills", "--out", d]), 0)
                self.assertFalse((Path(d) / "runs.json").exists())  # nothing ran, nothing recorded
