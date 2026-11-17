import json
import os
import subprocess
import unittest
from unittest import mock

from xplorekit import llm


def proc(code, out="", err=""):
    return subprocess.CompletedProcess([], code, out, err)


class TokenFallbackTests(unittest.TestCase):
    def setUp(self):
        llm.STATS.update({"calls": 0, "failures": 0, "token_slots_used": []})
        self.env = mock.patch.dict(os.environ, {"XK_LLM": "claude_cli", "CLAUDE_CODE_OAUTH_TOKEN": "tok-one", "CLAUDE_CODE_OAUTH_TOKEN_2": "tok-two"}, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_second_token_takes_over_when_the_first_fails(self):
        seen = []
        def fake(cmd, **k):
            seen.append(k["env"]["CLAUDE_CODE_OAUTH_TOKEN"])
            return proc(1, err="usage limit") if len(seen) == 1 else proc(0, json.dumps({"result": "hello"}))
        with mock.patch.object(llm.subprocess, "run", fake):
            self.assertEqual(llm.complete("hi"), "hello")
        self.assertEqual(seen, ["tok-one", "tok-two"])
        self.assertEqual((llm.STATS["calls"], llm.STATS["failures"], llm.STATS["token_slots_used"]), (2, 1, [2]))

    def test_all_failing_raises_without_leaking_token_values(self):
        with mock.patch.object(llm.subprocess, "run", lambda *a, **k: proc(1, err="tok-one tok-two")):
            with self.assertRaises(llm.LLMError) as cm:
                llm.complete("hi")
        msg = str(cm.exception)
        self.assertIn("slot 1", msg)
        self.assertNotIn("tok-one", msg)
        self.assertNotIn("tok-two", msg)

    def test_unset_gaps_are_skipped_and_slots_keep_their_number(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN_3": "tok-three"}):
            self.assertEqual([s for s, _ in llm.token_slots()], [1, 2, 3])
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(llm.token_slots(), [])
            self.assertEqual(llm.provider(), "none")


if __name__ == "__main__":
    unittest.main()


class UsageTests(unittest.TestCase):
    def test_cli_usage_is_summed(self):
        llm.reset_stats()
        with mock.patch.dict(os.environ, {"XK_LLM": "claude_cli", "CLAUDE_CODE_OAUTH_TOKEN": "t"}, clear=True):
            out = json.dumps({"result": "x", "num_turns": 1, "total_cost_usd": 0.01, "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100}})
            with mock.patch.object(llm.subprocess, "run", lambda *a, **k: proc(0, out)):
                llm.complete("a")
                llm.complete("b")
        t = llm.STATS["tokens"]
        self.assertEqual((t["input"], t["output"], t["cache_read"], t["turns"], t["cost_usd"]), (20, 10, 200, 2, 0.02))


class ExtractJsonTests(unittest.TestCase):
    def test_a_verdict_with_an_empty_issues_list_is_the_verdict_not_the_list(self):
        # regression: the extractor used to return [] here, so every fact-check was silently dropped ("rules_only")
        self.assertEqual(llm.extract_json('{"supported": true, "score": 90, "issues": []}', expect="object"), {"supported": True, "score": 90, "issues": []})
        self.assertEqual(llm.extract_json('{"supported": true, "score": 90, "issues": []}'), {"supported": True, "score": 90, "issues": []})

    def test_chatter_fences_and_nested_lists(self):
        self.assertEqual(llm.extract_json('Here you go:\n```json\n{"a": [1, 2], "b": {"c": []}}\n```\nDone.')["a"], [1, 2])
        self.assertEqual(llm.extract_json('Sure\n[{"a": [1,2]}, {"b": 2}]', expect="array"), [{"a": [1, 2]}, {"b": 2}])

    def test_expect_is_enforced_and_garbage_raises(self):
        with self.assertRaises(llm.LLMError):
            llm.extract_json('[1, 2]', expect="object")
        with self.assertRaises(llm.LLMError):
            llm.extract_json("no json here")


class FactCheckNeverSilentTests(unittest.TestCase):
    def test_verdict_comes_through_and_unreadable_answers_raise_after_one_retry(self):
        from xplorekit.agents import editor_verifier as ed
        calls = []
        with mock.patch.object(llm, "available", lambda: True), mock.patch.object(llm, "complete", lambda p, system="": calls.append(1) or '{"supported": true, "score": 91, "issues": []}'):
            self.assertEqual(ed.llm_fact_check("skills", {"name": "x"}, "text")["score"], 91)
        calls.clear()
        with mock.patch.object(llm, "available", lambda: True), mock.patch.object(llm, "complete", lambda p, system="": calls.append(1) or "I could not decide."):
            with self.assertRaises(llm.LLMError):
                ed.llm_fact_check("skills", {"name": "x"}, "text")
        self.assertEqual(len(calls), 2)  # one retry, then it raises instead of returning None

    def test_no_model_configured_is_the_only_case_that_returns_none(self):
        from xplorekit.agents import editor_verifier as ed
        with mock.patch.object(llm, "available", lambda: False):
            self.assertIsNone(ed.llm_fact_check("skills", {"name": "x"}, "text"))

    def test_a_failed_fact_check_rejects_the_draft_instead_of_publishing_it_unchecked(self):
        import tests.helpers as h
        from xplorekit.agents import editor_verifier as ed
        def boom(*a):
            raise llm.LLMError("fact-check unreadable after a retry")
        acc, rej = ed.review("skills", [h.DRAFTS["skills"]], h.ctx("skills", fact=boom))
        self.assertEqual((acc, rej[0]["reason"]), ([], "fact_check_failed"))
