import tempfile
import unittest
from pathlib import Path

from xplorekit import build_libraries


class LibraryTests(unittest.TestCase):
    def test_builds_three_pages_and_escapes_script_end(self):
        with tempfile.TemporaryDirectory() as d:
            data = Path(d) / "data"
            (data / "prompts").mkdir(parents=True)
            (data / "prompts" / "a.json").write_text('{"title":"T </script>","prompt":"p","use_case":"seo","source_url":"https://x.test","last_checked":"2026-01-01"}')
            out = Path(d) / "out"
            self.assertEqual(build_libraries.main(["--data-dir", str(data), "--out", str(out)]), 0)
            for s in ("prompts", "skills", "extensions"):
                self.assertTrue((out / s / "index.html").exists())
            html = (out / "prompts" / "index.html").read_text()
            self.assertIn("seo", html)
            self.assertNotIn("T </script>", html)
