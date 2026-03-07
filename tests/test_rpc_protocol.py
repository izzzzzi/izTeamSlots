from __future__ import annotations

import unittest

from backend.rpc_protocol import RPCError, make_error_response, make_event, make_success_response, parse_request


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
