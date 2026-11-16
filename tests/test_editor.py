import unittest

import tests.helpers as h
from xplorekit.agents import editor_verifier as editor


def run(section, draft=None, **kw):
    acc, rej = editor.review(section, [draft or h.DRAFTS[section]], h.ctx(section, **kw))
    return acc, rej


class EditorTests(unittest.TestCase):
    def test_good_draft_in_every_section_is_accepted_with_a_fact_check(self):
        for section in h.DRAFTS:
            acc, rej = run(section, fact=h.good_verdict)
            self.assertEqual((len(acc), rej), (1, []), section)
            e = acc[0]
            self.assertIn("fact_check:test", e["verified"])
            self.assertEqual((e["status"], e["section"]), ("active", section))
            self.assertRegex(e["id"], r"^[a-z0-9-]+-[0-9a-f]{6}$")

    def test_without_a_fact_check_money_cannot_pass_but_others_can(self):
        acc, rej = run("money")
        self.assertEqual((acc, rej[0]["reason"]), ([], "low_quality"))
        acc, _ = run("skills")
        self.assertEqual(acc[0]["verified"][-1], "rules_only")
        self.assertLess(acc[0]["quality_score"], 80)

    def test_dead_link_is_rejected(self):
        acc, rej = run("skills", link=("dead", 404), fact=h.good_verdict)
        self.assertEqual((acc, rej[0]["reason"]), ([], "dead_link"))

    def test_bot_blocked_link_is_accepted_but_labelled(self):
        acc, _ = run("skills", link=("blocked", 403), fact=h.good_verdict)
        self.assertIn("link_live_bot_blocked", acc[0]["verified"])

    def test_invented_income_number_is_rejected(self):
        d = {**h.DRAFTS["money"], "income": {**h.DRAFTS["money"]["income"], "low": 40, "high": 90}}
        acc, rej = run("money", d, fact=h.good_verdict)
        self.assertEqual((acc, rej[0]["reason"]), ([], "money_gate"))

    def test_money_without_a_figure_is_fine(self):
        d = {**h.DRAFTS["money"], "income": {"stated_in_source": False, "low": None, "high": None, "currency": "USD", "period": "none", "basis": "No verifiable income figure in the source; results vary."}}
        acc, _ = run("money", d, fact=h.good_verdict)
        self.assertIn("no_income_figure", acc[0]["verified"])

    def test_hype_is_rejected(self):
        d = {**h.DRAFTS["money"], "summary": "Guaranteed income with this secret method, quit your job today."}
        acc, rej = run("money", d, fact=h.good_verdict)
        self.assertEqual(rej[0]["reason"], "money_gate")

    def test_fact_check_failure_rejects(self):
        acc, rej = run("skills", fact=lambda *a: {"supported": False, "score": 30, "issues": ["install steps invented"]})
        self.assertEqual((acc, rej[0]["reason"]), ([], "fact_check"))
        self.assertIn("install steps invented", rej[0]["detail"])

    def test_copied_source_text_is_rejected(self):
        long = ("This skill teaches Claude to turn a messy changelog into clean, consistent release notes that follow a fixed house style, "
                "grouping every change by type and rewriting each line for readers instead of developers.")
        acc, rej = run("skills", {**h.DRAFTS["skills"], "summary": long}, text="Intro. " + long + " Outro.", fact=h.good_verdict)
        self.assertEqual(rej[0]["reason"], "copied_text")
        acc, _ = run("skills", {**h.DRAFTS["skills"], "summary": h.DRAFTS["skills"]["summary"]}, text=h.DRAFTS["skills"]["summary"], fact=h.good_verdict)
        self.assertEqual(len(acc), 1, "a short shared phrase under the limit is allowed")

    def test_schema_failure_and_non_store_url_rejected(self):
        acc, rej = run("extensions", {**h.DRAFTS["extensions"], "store_url": "https://example.com/not-the-store"}, fact=h.good_verdict)
        self.assertEqual(rej[0]["reason"], "schema")

    def test_duplicate_of_live_site_and_of_batch(self):
        site = [{"title": "example-skill", "urls": set(), "where": "site page skills-directory/x.html"}]
        acc, rej = editor.review("skills", [h.DRAFTS["skills"]], h.ctx("skills", fact=h.good_verdict, site_known=site))
        self.assertEqual(rej[0]["reason"], "duplicate")
        two = [h.DRAFTS["skills"], {**h.DRAFTS["skills"], "name": "Example Skill"}]
        acc, rej = editor.review("skills", two, h.ctx("skills", fact=h.good_verdict))
        self.assertEqual((len(acc), rej[0]["reason"]), (1, "duplicate"))

    def test_unverifiable_extension_date_becomes_unknown(self):
        d = {**h.DRAFTS["extensions"], "extension_last_updated": "2026-03-10"}
        acc, _ = run("extensions", d, fact=h.good_verdict)
        self.assertEqual(acc[0]["extension_last_updated"], "unknown")
        acc, _ = run("extensions", d, text=h.SOURCE_TEXT["extensions"] + " Updated March 10, 2026", fact=h.good_verdict)
        self.assertEqual(acc[0]["extension_last_updated"], "2026-03-10")

    def test_agent_cannot_set_editor_fields_or_invent_ids(self):
        d = {**h.DRAFTS["skills"], "id": "hacked", "quality_score": 100, "status": "stale", "verified": ["everything"]}
        acc, _ = run("skills", d, fact=h.good_verdict)
        self.assertNotEqual(acc[0]["id"], "hacked")
        self.assertEqual(acc[0]["status"], "active")
        self.assertNotIn("everything", acc[0]["verified"])

    def test_a_crash_in_one_draft_does_not_stop_the_batch(self):
        bad = {"title": 5}
        acc, rej = editor.review("skills", [bad, h.DRAFTS["skills"]], h.ctx("skills", fact=h.good_verdict))
        self.assertEqual((len(acc), len(rej)), (1, 1))


if __name__ == "__main__":
    unittest.main()
