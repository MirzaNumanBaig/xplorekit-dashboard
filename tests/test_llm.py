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
