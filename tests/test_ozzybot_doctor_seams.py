import sys
import unittest

sys.path.insert(0, "/home/rick/ozzy-bot")

from ozzybot_doctor import classify_state_file_consumers


class OzzyBotDoctorSeamTests(unittest.TestCase):
    def test_reporting_only_consumer_is_warning_not_green(self):
        status, reason = classify_state_file_consumers(["telegram_reporter.py (reporting only)"])

        self.assertEqual(status, "REPORTING_ONLY")
        self.assertIn("no execution consumer", reason)

    def test_execution_consumer_is_wired(self):
        status, reason = classify_state_file_consumers(["signal_generator.py", "telegram_reporter.py"])

        self.assertEqual(status, "WIRED")
        self.assertEqual(reason, "execution consumer present")


if __name__ == "__main__":
    unittest.main()
