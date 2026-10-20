import unittest

from dispatch_brain.classifier import classify
from dispatch_brain.config import load_models, load_routes
from dispatch_brain.router import Router


class TestRouter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = Router(load_routes(), load_models())

    def decide(self, text, **kw):
        return self.router.decide(classify(text, **kw))

    def test_simple_code_uses_cheap_model(self):
        d = self.decide("这段 python 代码报错，帮我看一下")
        self.assertEqual(d.model_alias, "deepseek-flash")
        self.assertEqual(d.reasoning, "low")

    def test_hard_task_escalates_to_strong_model(self):
        d = self.decide("帮我设计一个高并发的系统架构，并推导为什么这样设计")
        self.assertEqual(d.model_alias, "deepseek-v4-pro")
        self.assertEqual(d.reasoning, "high")

    def test_vision_goes_to_vision_model(self):
        d = self.decide("这是什么", has_image=True)
        self.assertEqual(d.model_alias, "qwen-vl-max")
        self.assertTrue(d.needs_vision)

    def test_deterministic_spends_no_tokens(self):
        d = self.decide("把这批照片批量重命名成日期格式")
        self.assertEqual(d.executor, "script")
        self.assertIsNone(d.model_alias)

    def test_high_risk_requires_human_confirm(self):
        d = self.decide("把这封邮件发送给客户")
        self.assertTrue(d.needs_human_confirm)

    def test_pins(self):
        cheap = self.router.pinned("auto-cheap")
        self.assertEqual(cheap.model_alias, "deepseek-flash")
        strong = self.router.pinned("auto-strong")
        self.assertEqual(strong.model_alias, "deepseek-v4-pro")
        self.assertIsNone(self.router.pinned("auto-nonexistent"))


if __name__ == "__main__":
    unittest.main()
