"""
Tests for toyopuc address parsing.
Compatible with both unittest and pytest.
"""

import unittest
from toyopuc.address import DataType, parse_address
from toyopuc.exceptions import ToyopucAddressError


class TestToyopucAddress(unittest.TestCase):

    def test_manual_examples(self):
        # Example from Manual 3-20: P1-M1000 -> 0x006E1800
        p1_m1000 = parse_address("P1-M1000", default_data_type=DataType.BIT)
        self.assertEqual(p1_m1000.logical_address, 0x006E1800)
        self.assertEqual(p1_m1000.data_type, DataType.BIT)
        self.assertEqual(p1_m1000.program_no, 1)

        # Example from Manual 3-20: P2-D2000L -> 0x000E6000
        p2_d2000l = parse_address("P2-D2000L", default_data_type=DataType.BYTE)
        self.assertEqual(p2_d2000l.logical_address, 0x000E6000)
        self.assertEqual(p2_d2000l.data_type, DataType.BYTE)
        self.assertEqual(p2_d2000l.program_no, 2)

    def test_basic_devices(self):
        # P1-M100
        m100 = parse_address("P1-M100", default_data_type=DataType.BIT)
        self.assertEqual(m100.logical_address, 0x00681900)

        # P1-M108
        m108 = parse_address("P1-M108", default_data_type=DataType.BIT)
        self.assertEqual(m108.logical_address, 0x00681908)

        # P1-D100
        d100 = parse_address("P1-D100", default_data_type=DataType.WORD)
        self.assertEqual(d100.logical_address, 0x000D2200)

        # Without program prefix (default P1)
        d100_no_p = parse_address("D100", default_data_type=DataType.WORD)
        self.assertEqual(d100_no_p.logical_address, 0x000D2200)

    def test_extended_devices(self):
        # U register: U0000 -> Ex No 0x03, byte offset 0x0000 -> 0x00030000
        u0 = parse_address("U0000", default_data_type=DataType.WORD)
        self.assertEqual(u0.logical_address, 0x00030000)

        # EB register: EB0000 -> Ex No 0x10, byte offset 0x0000 -> 0x00100000
        eb0 = parse_address("EB0000", default_data_type=DataType.WORD)
        self.assertEqual(eb0.logical_address, 0x00100000)

    def test_invalid_address(self):
        with self.assertRaises(ToyopucAddressError):
            parse_address("INVALID_ADDR")

        with self.assertRaises(ToyopucAddressError):
            parse_address("P5-M100")


if __name__ == "__main__":
    unittest.main()
