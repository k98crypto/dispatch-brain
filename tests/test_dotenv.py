import os
import tempfile
import unittest
from pathlib import Path

from dispatch_brain.config import load_dotenv


class TestLoadDotenv(unittest.TestCase):
    def test_loads_values_and_respects_existing_env(self):
        with tempfile.TemporaryDirectory() as d:
            env_file = Path(d) / ".env"
            env_file.write_text(
                "# comment\n"
                "DBRAIN_TEST_A=from_file\n"
                'DBRAIN_TEST_B="quoted value"\n'
                "DBRAIN_TEST_C=should_not_win\n"
                "\n"
                "broken line without equals\n",
                encoding="utf-8",
            )
            os.environ.pop("DBRAIN_TEST_A", None)
            os.environ.pop("DBRAIN_TEST_B", None)
            os.environ["DBRAIN_TEST_C"] = "from_shell"
            try:
                load_dotenv(env_file)
                self.assertEqual(os.environ["DBRAIN_TEST_A"], "from_file")
                self.assertEqual(os.environ["DBRAIN_TEST_B"], "quoted value")
                self.assertEqual(os.environ["DBRAIN_TEST_C"], "from_shell")
            finally:
                os.environ.pop("DBRAIN_TEST_A", None)
                os.environ.pop("DBRAIN_TEST_B", None)
                os.environ.pop("DBRAIN_TEST_C", None)

    def test_missing_file_is_silent(self):
        load_dotenv(Path("/nonexistent/.env"))  # must not raise


if __name__ == "__main__":
    unittest.main()
