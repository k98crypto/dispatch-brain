import tempfile
import unittest
from pathlib import Path

from dispatch_brain.logstore import LogStore


class TestLogStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LogStore(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_record_and_stats(self):
        for _ in range(6):
            self.store.record("code", "deepseek-flash", True, tokens=1000, latency_ms=500)
        for _ in range(6):
            self.store.record("code", "deepseek-v4-pro", True, tokens=9000, latency_ms=2000)
        stats = {(s["scene"], s["model_alias"]): s for s in self.store.stats()}
        self.assertEqual(stats[("code", "deepseek-flash")]["n"], 6)
        self.assertEqual(stats[("code", "deepseek-flash")]["success_rate"], 1.0)

    def test_suggest_prefers_cost_effective(self):
        for _ in range(6):
            self.store.record("chat", "deepseek-flash", True, tokens=1000)
        for _ in range(6):
            self.store.record("chat", "deepseek-v4-pro", True, tokens=9000)
        sug = self.store.suggest(min_samples=5)
        self.assertEqual(sug["chat"]["best"]["model_alias"], "deepseek-flash")

    def test_suggest_marks_insufficient_data(self):
        self.store.record("chat", "deepseek-flash", True, tokens=100)
        sug = self.store.suggest(min_samples=5)
        self.assertIsNone(sug["chat"]["best"])
        self.assertEqual(sug["chat"]["candidates"][0]["verdict"], "insufficient_data")


if __name__ == "__main__":
    unittest.main()
