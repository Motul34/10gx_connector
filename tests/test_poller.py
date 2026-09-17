"""
Tests for BackgroundPoller and client polling controls.
Compatible with both unittest and pytest.
"""

import time
import unittest
import toyopuc
from toyopuc.mock_server import MockToyopucServer


class TestBackgroundPoller(unittest.TestCase):
    server: MockToyopucServer
    port: int

    @classmethod
    def setUpClass(cls):
        cls.server = MockToyopucServer()
        cls.port = cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_background_polling(self):
        with toyopuc.connect("127.0.0.1", self.port) as plc:
            # Initial values
            plc.bit_write({"P1-M100": 1})
            plc.word_write({"P1-D100": 100})

            # Start background polling at fast interval for testing
            poller = plc.start_polling(["P1-M100", "P1-D100"], interval=0.05)
            self.assertTrue(poller.is_running)

            # Give it a moment to complete first poll
            time.sleep(0.15)
            self.assertEqual(poller.get("P1-M100"), 1)
            self.assertEqual(poller.get("P1-D100"), 100)

            # Change PLC values via client write (thread-safe)
            plc.word_write({"P1-D100": 999})
            plc.bit_write({"P1-M100": 0})

            # Wait for poller to pick up changes
            time.sleep(0.15)
            self.assertEqual(poller.get("P1-M100"), 0)
            self.assertEqual(poller.get("P1-D100"), 999)
            self.assertEqual(poller.get_latest(), {"P1-M100": 0, "P1-D100": 999})

            # Test stopping via client.stop_polling()
            plc.stop_polling(poller)
            self.assertFalse(poller.is_running)

    def test_stop_all_polling(self):
        with toyopuc.connect("127.0.0.1", self.port) as plc:
            p1 = plc.start_polling(["P1-M100"], interval=0.1)
            p2 = plc.start_polling(["P1-D100"], interval=0.1)
            self.assertTrue(p1.is_running)
            self.assertTrue(p2.is_running)

            plc.stop_polling()  # Stop all
            self.assertFalse(p1.is_running)
            self.assertFalse(p2.is_running)


if __name__ == "__main__":
    unittest.main()
