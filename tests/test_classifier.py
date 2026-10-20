import unittest

from dispatch_brain.classifier import classify


class TestClassifier(unittest.TestCase):
    def test_deterministic_rename_goes_to_script(self):
        c = classify("把这批照片批量重命名成日期格式")
        self.assertEqual(c.scene, "deterministic")
        self.assertEqual(c.executor, "script")

    def test_vision_by_keyword(self):
        c = classify("看一下这张截图里写了什么")
        self.assertEqual(c.scene, "vision")
        self.assertTrue(c.needs_vision)

    def test_vision_by_image_flag(self):
        c = classify("这是什么", has_image=True)
        self.assertEqual(c.scene, "vision")
        self.assertTrue(c.needs_vision)

    def test_code_simple(self):
        c = classify("这段 python 代码报错，帮我看一下")
        self.assertEqual(c.scene, "code")

    def test_code_hard(self):
        c = classify("帮我设计一个高并发的系统架构，并推导为什么这样设计")
        self.assertEqual(c.difficulty, "hard")

    def test_risk_send_is_high(self):
        c = classify("把这封邮件发送给客户")
        self.assertEqual(c.risk, "high")

    def test_risk_delete_is_high(self):
        c = classify("delete the temp files and send it to me")
        self.assertEqual(c.risk, "high")

    def test_short_chat_is_simple(self):
        c = classify("你好")
        self.assertEqual(c.scene, "chat")
        self.assertEqual(c.difficulty, "simple")


if __name__ == "__main__":
    unittest.main()
