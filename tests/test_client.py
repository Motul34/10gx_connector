"""
Integration tests for ToyopucClient using MockToyopucServer.
Compatible with both unittest and pytest.
"""

import unittest
import toyopuc
from toyopuc.mock_server import MockToyopucServer


class TestToyopucClient(unittest.TestCase):
    server: MockToyopucServer
    port: int

    @classmethod
    def setUpClass(cls):
        cls.server = MockToyopucServer()
        cls.port = cls.server.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_connection_properties(self):
        plc = toyopuc.connect("127.0.0.1", self.port)
        self.assertTrue(plc.is_connected)
        plc.disconnect()
        self.assertFalse(plc.is_connected)

    def test_bit_read_write(self):
        with toyopuc.connect("127.0.0.1", self.port) as plc:
            # Single write via dict & single address write
            plc.bit_write({"P1-M100": 1})
            self.assertEqual(plc.bit_read("P1-M100")[0], 1)

            plc.bit_write("P1-M108", 1)
            self.assertEqual(plc.bit_read("P1-M108")[0], 1)

            # Multiple read (different addresses, scattered)
            vals = plc.bit_read("P1-M100", "P1-M108", "P1-M101")
            self.assertEqual(vals, [1, 1, 0])

            # List argument
            vals = plc.bit_read(["P1-M100", "P1-M108"])
            self.assertEqual(vals, [1, 1])

            # Multiple write via dict
            plc.bit_write({
                "P1-M100": 0,
                "P1-M108": 0,
                "P2-M200": 1,
            })
            self.assertEqual(plc.bit_read("P1-M100")[0], 0)
            self.assertEqual(plc.bit_read("P1-M108")[0], 0)
            self.assertEqual(plc.bit_read("P2-M200")[0], 1)

    def test_word_read_write(self):
        with toyopuc.connect("127.0.0.1", self.port) as plc:
            # Single write & read
            plc.word_write({"P1-D100": 12345})
            self.assertEqual(plc.word_read("P1-D100")[0], 12345)

            # Multiple words across different programs & registers
            plc.word_write({
                "P1-D100": 1111,
                "P1-D200": 2222,
                "P2-D100": 3333,
                "U0000": 4444,
            })

            res = plc.word_read("P1-D100", "P1-D200", "P2-D100", "U0000")
            self.assertEqual(res, [1111, 2222, 3333, 4444])

    def test_byte_read_write(self):
        with toyopuc.connect("127.0.0.1", self.port) as plc:
            plc.byte_write({"P1-D100L": 0x34, "P1-D100H": 0x12})
            self.assertEqual(plc.byte_read("P1-D100L")[0], 0x34)
            self.assertEqual(plc.byte_read("P1-D100H")[0], 0x12)
            # As word, it should be 0x1234 = 4660
            self.assertEqual(plc.word_read("P1-D100")[0], 0x1234)

    def test_long_read_write(self):
        with toyopuc.connect("127.0.0.1", self.port) as plc:
            # 32-bit integer write & read
            plc.long_write({"P1-D100": 0x12345678, "P1-D200": 100000})
            vals = plc.long_read("P1-D100", "P1-D200")
            self.assertEqual(vals, [0x12345678, 100000])

    def test_read_mixed(self):
        with toyopuc.connect("127.0.0.1", self.port) as plc:
            plc.bit_write({"P1-M100": 1})
            plc.word_write({"P1-D100": 500})

            mixed = plc.read_mixed(["P1-M100", "P1-D100"])
            self.assertEqual(mixed, {"P1-M100": 1, "P1-D100": 500})

    def test_chunking_large_read_and_write(self):
        with toyopuc.connect("127.0.0.1", self.port) as plc:
            # Generate 150 word addresses (exceeds 127 point limit of single command)
            addresses = [f"P1-D{i}" for i in range(150)]
            write_dict = {addr: i * 10 for i, addr in enumerate(addresses)}

            written = plc.word_write(write_dict)
            self.assertEqual(written, 150)

            read_vals = plc.word_read(addresses)
            self.assertEqual(len(read_vals), 150)
            self.assertEqual(read_vals[0], 0)
            self.assertEqual(read_vals[10], 100)
            self.assertEqual(read_vals[149], 1490)


if __name__ == "__main__":
    unittest.main()
