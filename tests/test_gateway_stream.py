import unittest

from dispatch_brain.gateway import _usage_from_sse_line


class TestUsageFromSseLine(unittest.TestCase):
    def test_usage_line(self):
        line = b'data: {"id":"x","choices":[],"usage":{"total_tokens":42,"prompt_tokens":10,"completion_tokens":32}}'
        self.assertEqual(_usage_from_sse_line(line), 42)

    def test_chunk_without_usage(self):
        line = b'data: {"id":"x","choices":[{"delta":{"content":"hi"}}]}'
        self.assertEqual(_usage_from_sse_line(line), 0)

    def test_done_marker(self):
        self.assertEqual(_usage_from_sse_line(b"data: [DONE]"), 0)

    def test_non_data_lines(self):
        self.assertEqual(_usage_from_sse_line(b": comment"), 0)
        self.assertEqual(_usage_from_sse_line(b""), 0)
        self.assertEqual(_usage_from_sse_line(b"event: ping"), 0)

    def test_malformed_json(self):
        self.assertEqual(_usage_from_sse_line(b"data: {not json"), 0)

    def test_zero_usage(self):
        line = b'data: {"usage":{"total_tokens":0}}'
        self.assertEqual(_usage_from_sse_line(line), 0)


if __name__ == "__main__":
    unittest.main()
