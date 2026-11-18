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
            self.assertEqual(money["caps"], {"daily": 1, "weekly": 3})
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

    def test_page_talks_only_to_the_github_api_and_the_browser_enforces_it(self):
        import re
        t = bd.TEMPLATE.read_text("utf-8")
        self.assertNotRegex(t, r'<script[^>]+src=')
        self.assertNotRegex(t, r'<link[^>]+href="https?:')
        self.assertNotIn("innerHTML", t)  # all dynamic text goes through textContent
        # exactly one network call site, and it can only reach the GitHub API
        self.assertEqual(len(re.findall(r"\bfetch\(", t)), 1)
        self.assertIn('fetch(API+path', t)
        self.assertEqual(re.findall(r'API="(https?://[^"]+)"', t), ["https://api.github.com"])
        # the browser itself blocks anything else (a CSP, so even injected code could not send the token elsewhere)
        csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', t).group(1)
        self.assertIn("default-src 'none'", csp)
        self.assertIn("connect-src https://api.github.com;", csp)
        self.assertNotRegex(csp, r"script-src[^;]*(https?:|\*)")
        # the token goes in a header only: never in a URL, never logged
        self.assertNotRegex(t, r"access_token|[?&]token=|console\.log")
        self.assertIn('h.Authorization="Bearer "+t', t)

    def test_the_token_is_remembered_only_when_asked_and_can_be_forgotten(self):
        t = bd.TEMPLATE.read_text("utf-8")
        self.assertIn("sessionStorage", t)          # default: gone when the tab closes
        self.assertIn("rem.checked", t)             # localStorage only after the visitor ticks "remember"
        self.assertIn("Forget token", t)


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


class UsageTotalsTests(unittest.TestCase):
    def test_periods_and_dry_runs(self):
        day = "2026-11-16"
        run = lambda d, n, dry=False: {"type": "research", "date": d, "dry_run": dry, "llm": {"tokens": {"input": n, "output": 1, "turns": 1, "cost_usd": 0.5}}}
        u = bd.usage([run(day, 10), run("2026-11-12", 20), run("2026-10-20", 40), run(day, 999, True)], day)
        self.assertEqual((u["today"]["input"], u["7d"]["input"], u["30d"]["input"], u["30d"]["runs"]), (10, 30, 70, 3))


class SiteDeliveryHealthTests(unittest.TestCase):
    def test_a_pr_held_back_for_a_human_and_a_failed_delivery_are_shown(self):
        held = {"state": "open_for_review", "pr": 80, "reason": "a hub page changed outside the generated feed block"}
        out = bd.health([research_run()], [], today(), held)
        self.assertEqual(out[0]["level"], "warn")
        self.assertIn("NOT merged automatically (PR #80)", out[0]["text"])
        bad = bd.health([research_run()], [], today(), {"state": "error", "reason": "build-feed.py failed"})
        self.assertEqual(bad[0]["level"], "bad")
        merged = bd.health([research_run()], [], today(), {"state": "merged", "pr": 81})
        self.assertEqual([x["level"] for x in merged], ["ok"])


class PostsTests(unittest.TestCase):
    def posts(self, d):
        return {p["id"]: p for p in bd.build_dataset(d)["posts"]}

    def test_each_entry_gets_one_of_the_five_states(self):
        with tempfile.TemporaryDirectory() as d:
            pub = write_entry(d, "skills", name="Published one")
            pend = write_entry(d, "extensions", name="Waiting one")
            draft = write_entry(d, "prompts", title="Unchecked one", verified=["schema", "rules_only"])
            stale = write_entry(d, "money", title="Withdrawn one", status="stale")
            Path(d, "published.json").write_text(json.dumps({pub["id"]: {"section": "skills", "published_at": "2026-11-17", "pr": 80, "withdrawn_at": None}}))
            Path(d, "rejected").mkdir()
            Path(d, "rejected", "money.json").write_text(json.dumps([{"title": "Hype idea", "url": "https://x.com/h", "reason": "money_gate", "detail": "hype wording", "date": "2026-11-17"}]))
            ds = bd.build_dataset(d)
            by = {p["id"]: p for p in ds["posts"]}
            self.assertEqual([by[pub["id"]]["state"], by[pend["id"]]["state"], by[draft["id"]]["state"], by[stale["id"]]["state"]], ["published", "pending", "draft", "stale"])
            self.assertEqual(ds["post_counts"], {"published": 1, "pending": 1, "draft": 1, "stale": 1, "rejected": 1})
            rej = [p for p in ds["posts"] if p["state"] == "rejected"][0]
            self.assertEqual((rej["title"], rej["fields"]["why it was rejected"]), ("Hype idea", "Income claim not backed by the source."))

    def test_only_published_posts_link_to_the_live_site_and_carry_date_and_pr(self):
        with tempfile.TemporaryDirectory() as d:
            pub = write_entry(d, "skills", name="Live one")
            pend = write_entry(d, "extensions", name="Not live one")
            Path(d, "published.json").write_text(json.dumps({pub["id"]: {"section": "skills", "published_at": "2026-11-17", "pr": 80, "withdrawn_at": None}}))
            by = self.posts(d)
            live = by[pub["id"]]
            self.assertEqual(live["live_url"], f"https://xplorekit.online/research/skills/{pub['id']}")
            self.assertEqual((live["published_at"], live["pr"]), ("2026-11-17", 80))
            self.assertIsNone(by[pend["id"]]["live_url"])

    def test_a_withdrawn_entry_that_is_still_fact_checked_goes_back_to_pending_not_published(self):
        with tempfile.TemporaryDirectory() as d:
            e = write_entry(d, "skills", name="Came back")
            Path(d, "published.json").write_text(json.dumps({e["id"]: {"section": "skills", "published_at": "2026-11-10", "pr": 70, "withdrawn_at": "2026-11-12"}}))
            self.assertEqual(self.posts(d)[e["id"]]["state"], "pending")

    def test_details_carry_the_content_but_not_internal_bookkeeping(self):
        with tempfile.TemporaryDirectory() as d:
            e = write_entry(d, "money")
            f = self.posts(d)[e["id"]]["fields"]
            self.assertIn("workflow_steps", f)
            self.assertIn("income", f)
            for hidden in ("id", "verified", "quality_score", "source_urls", "first_seen"):
                self.assertNotIn(hidden, f)

    def test_the_newest_published_come_first_and_counts_appear_on_the_section_cards(self):
        with tempfile.TemporaryDirectory() as d:
            old = write_entry(d, "skills", name="Older live", first_seen="2026-11-01")
            new = write_entry(d, "extensions", name="Newer live", first_seen="2026-11-10")
            Path(d, "published.json").write_text(json.dumps({old["id"]: {"section": "skills", "published_at": "2026-11-02", "pr": 1, "withdrawn_at": None},
                                                              new["id"]: {"section": "extensions", "published_at": "2026-11-11", "pr": 2, "withdrawn_at": None}}))
            ds = bd.build_dataset(d)
            self.assertEqual([p["id"] for p in ds["posts"][:2]], [new["id"], old["id"]])
            self.assertEqual({s["key"]: s["stats"]["published"] for s in ds["sections"]}["extensions"], 1)


class ControlInfoTests(unittest.TestCase):
    def test_schedule_is_read_from_the_workflow_file_not_hard_coded(self):
        s = bd.schedule_info()
        self.assertEqual(s, {"minute": 17, "every_hours": 3})  # research.yml: cron "17 */3 * * *"

    def test_dataset_carries_what_the_control_bar_needs(self):
        with tempfile.TemporaryDirectory() as d:
            c = bd.build_dataset(d)["control"]
            self.assertEqual((c["workflow"], c["settings_path"], c["branch"]), ("research.yml", "xplorekit/config/settings.json", "main"))
            self.assertIn(c["publish_mode"], ("publish", "pending", "draft"))
            self.assertIsInstance(c["paused"], bool)

    def test_a_mode_other_than_publish_shows_a_warning_that_names_the_fix(self):
        from unittest import mock
        for mode, word in (("draft", "nothing is sent"), ("pending", "waits for a person")):
            with mock.patch.object(bd, "publish_mode", lambda m=mode: m):
                first = bd.health([research_run()], [], today())[0]
            self.assertEqual(first["level"], "warn")
            self.assertIn(word, first["text"])
        with mock.patch.object(bd, "publish_mode", lambda: "publish"):
            self.assertEqual([x["level"] for x in bd.health([research_run()], [], today())], ["ok"])


class TokenCheckTests(unittest.TestCase):
    def test_the_page_can_only_read_post_and_put_and_posts_are_limited_to_two_harmless_calls(self):
        import re
        t = bd.TEMPLATE.read_text("utf-8")
        methods = set(re.findall(r'api\("(\w+)"', t))
        self.assertEqual(methods, {"GET", "POST", "PUT"})                     # never DELETE or PATCH: the page cannot remove or rewrite things
        self.assertEqual(len(re.findall(r'api\("POST"', t)), 2)               # starting a run, and the unused-object probe in Check token
        self.assertIn("/git/blobs", t)
        self.assertEqual(len(re.findall(r'api\("PUT"', t)), 1)                # the single settings.json write

    def test_errors_name_the_step_the_permission_and_quote_github(self):
        t = bd.TEMPLATE.read_text("utf-8")
        for needle in ("Contents: Read and write", "Actions: Read and write", "Only select repositories", "GitHub says:", "Check token", "xplorekit-dashboard"):
            self.assertIn(needle, t)
        self.assertNotIn("missing a permission", t)  # the old one-sentence message that hid which call failed

    def test_check_token_never_triggers_a_run_or_rewrites_the_settings_file(self):
        import re
        t = bd.TEMPLATE.read_text("utf-8")
        body = t[t.index("function checkToken()"):t.index("/* connect panel */")]
        self.assertNotIn("dispatches", body)
        self.assertNotIn('api("PUT"', body)
        self.assertNotIn("putSetting", body)


class ReworkTests(unittest.TestCase):
    def test_page_has_the_new_tabs_and_the_dataset_carries_reasons_and_entry_page_links(self):
        from xplorekit import build_dashboard as bd
        html = bd.TEMPLATE.read_text("utf-8")
        for tab in ('["activity","Activity"]', '["how","How it works"]'):
            self.assertIn(tab, html)
        self.assertNotIn('["rejected","Rejected"]', html)  # rejections live in Posts (status filter) and Activity
        self.assertNotIn('["runs","Runs"]', html)
        ds = bd.build_dataset(bd.ROOT / "data")
        self.assertIn("duplicate", ds["reasons"])
        self.assertIn("section_pages", ds)
        self.assertIn("per_run_max", ds["settings"])
