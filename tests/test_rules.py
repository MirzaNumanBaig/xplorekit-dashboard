import unittest

import tests.helpers as h
from xplorekit.common import canon_key
from xplorekit.verify import dedupe, rules


def money(**inc):
    return {"income": {"stated_in_source": True, "low": 15, "high": 25, "currency": "USD", "period": "hour", "basis": "published pay range", **inc}}


class RuleTests(unittest.TestCase):
    def test_hype_wording_is_caught(self):
        for bad in ("Guaranteed income every month", "Get rich quick with AI", "quit your 9-to-5 now", "make $500 a day"):
            self.assertTrue(rules.hype_problems({"summary": bad}), bad)
        self.assertEqual(rules.hype_problems({"summary": "Results vary and income is not guaranteed to be steady."}), [])

    def test_income_must_be_in_the_source(self):
        self.assertEqual(rules.income_problems(money(), "pay is 15 to 25 per hour"), [])
        self.assertTrue(rules.income_problems(money(), "pay is 10 to 20 per hour"))
        self.assertTrue(rules.income_problems(money(), ""))

    def test_invented_numbers_and_unrealistic_caps_are_rejected(self):
        self.assertTrue(rules.income_problems(money(stated_in_source=False), "15 25"))
        self.assertEqual(rules.income_problems(money(stated_in_source=False, low=None, high=None, period="none"), ""), [])
        self.assertTrue(any("cap" in p for p in rules.income_problems(money(low=5000, high=60000, period="month"), "5000 60000")))
        self.assertTrue(rules.income_problems(money(low=30, high=10), "30 10"))

    def test_verbatim_copy_detected(self):
        src = "The quick brown fox jumps over the lazy dog while the sun sets slowly behind the hills and everyone watches quietly from the porch of the old farm."
        self.assertTrue(rules.copy_problems({"summary": src}, src))
        self.assertEqual(rules.copy_problems({"summary": "A fox hops a dog at dusk."}, src), [])

    def test_staleness(self):
        old = {"last_checked": "2020-01-01"}
        self.assertTrue(rules.is_stale("extensions", old))
        self.assertFalse(rules.is_stale("extensions", {"last_checked": rules.today()}))


class DedupeTests(unittest.TestCase):
    def test_same_url_ignoring_tracking_and_www(self):
        a = {"title": "A", "urls": {canon_key("https://example.com/x")}, "where": "live site"}
        self.assertIn("same URL", dedupe.find_duplicate({"title": "Other", "source_urls": ["https://www.example.com/x/?utm_source=a#top"]}, [a]))

    def test_similar_titles(self):
        k = [{"title": "Get paid to train AI models", "urls": set(), "where": "site"}]
        self.assertTrue(dedupe.find_duplicate({"title": "Get Paid To Train AI Model", "source_urls": []}, k))
        self.assertIsNone(dedupe.find_duplicate({"title": "Sell printables on Gumroad", "source_urls": []}, k))


if __name__ == "__main__":
    unittest.main()
