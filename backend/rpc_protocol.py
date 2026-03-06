from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class RPCRequest:
    request_id: str
    method: str
    params: dict[str, Any]


class RPCError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        self.code = code
        self.message = message
        self.data = data or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "code": self.code,
            "message": self.message,
        }
        if self.data:
            out["data"] = self.data
        return out


def parse_request(line: str) -> RPCRequest:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as e:
        raise RPCError(-32700, "Parse error", {"details": str(e)}) from e

    if not isinstance(payload, dict):
        raise RPCError(-32600, "Invalid request", {"details": "payload must be object"})

    request_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params", {})

    if not isinstance(request_id, str) or not request_id:
        raise RPCError(-32600, "Invalid request", {"details": "id must be non-empty string"})
    if not isinstance(method, str) or not method:
        raise RPCError(-32600, "Invalid request", {"details": "method must be non-empty string"})
    if not isinstance(params, dict):
        raise RPCError(-32602, "Invalid params", {"details": "params must be object"})

    return RPCRequest(request_id=request_id, method=method, params=params)


def make_success_response(request_id: str, result: Any) -> dict[str, Any]:
    return {
        "type": "response",
        "id": request_id,
        "ok": True,
        "result": result,
    }


def make_error_response(request_id: str, error: RPCError) -> dict[str, Any]:
    return {
        "type": "response",
        "id": request_id,
        "ok": False,
        "error": error.to_dict(),
    }


def make_event(event: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "event",
        "event": event,
        "data": data,
    }
