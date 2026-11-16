import unittest

import tests.helpers as h
from xplorekit.agents import editor_verifier as editor
from xplorekit.verify.schema import load_schema, validate


class SchemaTests(unittest.TestCase):
    def test_every_section_has_a_schema_and_a_valid_sample(self):
        for section, draft in h.DRAFTS.items():
            entry = editor.finalize(section, draft)
            entry["quality_score"], entry["verified"] = 80, ["schema"]
            self.assertEqual(validate(entry, load_schema(section)), [], section)

    def test_missing_and_extra_fields_are_reported(self):
        e = editor.finalize("skills", h.DRAFTS["skills"])
        del e["repo_url"]
        e["surprise"] = 1
        errs = " ".join(validate(e, load_schema("skills")))
        self.assertIn("missing required field 'repo_url'", errs)
        self.assertIn("unexpected field 'surprise'", errs)

    def test_type_enum_pattern_and_length_checks(self):
        e = editor.finalize("extensions", {**h.DRAFTS["extensions"], "pricing": "cheap", "store_url": "https://example.com/x", "pros": []})
        errs = " ".join(validate(e, load_schema("extensions")))
        self.assertIn("not one of", errs)
        self.assertIn("pattern", errs)
        self.assertIn("fewer than 1 items", errs)

    def test_money_income_rejects_text_numbers(self):
        e = editor.finalize("money", {**h.DRAFTS["money"], "income": {**h.DRAFTS["money"]["income"], "low": "lots"}})
        self.assertTrue(any("income.low" in x for x in validate(e, load_schema("money"))))


if __name__ == "__main__":
    unittest.main()
