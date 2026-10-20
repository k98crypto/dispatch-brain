import unittest

from dispatch_brain.watchdog import Watchdog


class TestWatchdog(unittest.TestCase):
    def test_normal_steps_ok(self):
        w = Watchdog()
        for i in range(5):
            self.assertEqual(w.observe("read_file", f"f{i}.txt", f"state{i}", 100), "ok")

    def test_repeat_triggers_replan_then_stop(self):
        w = Watchdog(repeat_limit=3)
        self.assertEqual(w.observe("click", "btn", "s1"), "ok")
        self.assertEqual(w.observe("click", "btn", "s1"), "ok")
        self.assertEqual(w.observe("click", "btn", "s1"), "replan_escalate")
        # after the one allowed re-plan, the same loop must stop the run
        verdict = "ok"
        for _ in range(3):
            verdict = w.observe("click", "btn", "s1")
        self.assertEqual(verdict, "stop")

    def test_token_budget_stops(self):
        w = Watchdog(max_tokens=1000)
        self.assertEqual(w.observe("think", "", "s", tokens_used=600), "ok")
        self.assertEqual(w.observe("think", "", "s2", tokens_used=600), "stop")

    def test_step_budget_stops(self):
        w = Watchdog(max_steps=2)
        w.observe("a", "", "s1")
        w.observe("a", "", "s2")
        self.assertEqual(w.observe("a", "", "s3"), "stop")


if __name__ == "__main__":
    unittest.main()
