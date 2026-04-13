from __future__ import annotations

import unittest

from backend.rpc_protocol import RPCError, make_error_response, make_event, make_success_response, parse_request
from backend.rpc_server import RPCServer


class TestRPCProtocol(unittest.TestCase):
    def test_parse_request_success(self) -> None:
        req = parse_request('{"id":"1","method":"ping","params":{"x":1}}')
        self.assertEqual(req.request_id, "1")
        self.assertEqual(req.method, "ping")
        self.assertEqual(req.params, {"x": 1})

    def test_parse_request_rejects_invalid_payloads(self) -> None:
        with self.assertRaises(RPCError) as bad_json:
            parse_request("{")
        self.assertEqual(bad_json.exception.code, -32700)

        with self.assertRaises(RPCError) as bad_id:
            parse_request('{"id":"","method":"ping"}')
        self.assertEqual(bad_id.exception.code, -32600)

        with self.assertRaises(RPCError) as bad_params:
            parse_request('{"id":"1","method":"ping","params":[]}')
        self.assertEqual(bad_params.exception.code, -32602)

    def test_response_helpers(self) -> None:
        err = RPCError(-1, "boom", {"detail": "x"})

        self.assertEqual(make_success_response("1", {"ok": True})["ok"], True)
        self.assertEqual(make_error_response("1", err)["error"]["message"], "boom")
        self.assertEqual(make_event("job.done", {"id": "1"})["type"], "event")


class TestMaskSettingValue(unittest.TestCase):
    def test_empty_value_returns_empty(self) -> None:
        self.assertEqual(RPCServer._mask_setting_value("BOOMLIFY_API_KEY", ""), "")

    def test_short_key_fully_masked(self) -> None:
        self.assertEqual(RPCServer._mask_setting_value("BOOMLIFY_API_KEY", "abc123"), "***")

    def test_long_key_shows_only_first_and_last_two(self) -> None:
        key = "sk-abcdefghijklmnop"  # 18 chars
        masked = RPCServer._mask_setting_value("BOOMLIFY_API_KEY", key)
        self.assertEqual(masked, "sk***op")
        self.assertNotIn("abcdef", masked)

    def test_medium_key_fully_masked(self) -> None:
        key = "1234567890123"  # 13 chars
        masked = RPCServer._mask_setting_value("BOOMLIFY_API_KEY", key)
        self.assertEqual(masked, "***")

    def test_non_key_setting_not_masked(self) -> None:
        self.assertEqual(RPCServer._mask_setting_value("BOOMLIFY_DOMAIN", "example.com"), "example.com")
