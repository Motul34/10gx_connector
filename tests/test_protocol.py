"""
Tests for toyopuc protocol framing and parsing.
Compatible with both unittest and pytest.
"""

import unittest
from toyopuc.address import DataType, parse_address
from toyopuc.exceptions import ToyopucError, ToyopucResponseError
from toyopuc.protocol import (
    CMD_PC10_MULTI_READ,
    CMD_PC10_MULTI_WRITE,
    build_frame,
    build_pc10_multi_read_request,
    build_pc10_multi_write_request,
    parse_pc10_multi_read_response,
    parse_response_frame,
)


class TestToyopucProtocol(unittest.TestCase):

    def test_build_and_parse_frame(self):
        req = build_frame(0xC4, b"\x01\x02\x03")
        # Header: FT(00 00), TransferCount(4 = 1 cmd + 3 data), CMD(C4)
        self.assertEqual(req[:5], b"\x00\x00\x04\x00\xC4")
        self.assertEqual(req[5:], b"\x01\x02\x03")

        # Valid response
        resp = b"\x80\x00\x04\x00\xC4\xAA\xBB\xCC"
        payload = parse_response_frame(resp, expected_cmd=0xC4)
        self.assertEqual(payload, b"\xAA\xBB\xCC")

    def test_error_response_frame(self):
        # Error response: 80 10 01 00 23 (Invalid command)
        err_resp = b"\x80\x10\x01\x00\x23"
        with self.assertRaises(ToyopucResponseError) as ctx:
            parse_response_frame(err_resp, expected_cmd=0xC4)
        self.assertEqual(ctx.exception.response_code, 0x10)
        self.assertEqual(ctx.exception.error_code, 0x23)

    def test_multi_read_request_and_response_parsing(self):
        addrs = [
            parse_address("P1-M100", default_data_type=DataType.BIT),
            parse_address("P1-M108", default_data_type=DataType.BIT),
            parse_address("P1-D100", default_data_type=DataType.WORD),
        ]
        req = build_pc10_multi_read_request(addrs)
        self.assertEqual(req[4], CMD_PC10_MULTI_READ)

        # Mock response payload for 2 bits (1, 0) and 1 word (1234 = 0x04D2)
        payload = b"\x02\x00\x01\x00" + b"\x01" + b"\xD2\x04"
        vals = parse_pc10_multi_read_response(payload, addrs)
        self.assertEqual(vals, [1, 0, 1234])

    def test_multi_write_request(self):
        items = [
            (parse_address("P1-M100", default_data_type=DataType.BIT), 1),
            (parse_address("P1-D100", default_data_type=DataType.WORD), 5678),
        ]
        req = build_pc10_multi_write_request(items)
        self.assertEqual(req[4], CMD_PC10_MULTI_WRITE)


if __name__ == "__main__":
    unittest.main()
