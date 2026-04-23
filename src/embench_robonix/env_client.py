"""Thin JSON-over-UNIX-socket client used by each skill MCP server to
reach the shared EB-Habitat env adapter. Keeps skill processes stateless.
"""
from __future__ import annotations

import json
import socket
from typing import Any


class EnvClient:
    def __init__(self, sock_path: str) -> None:
        self._path = sock_path

    def call(self, method: str, params: dict[str, Any]) -> dict:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self._path)
        try:
            payload = json.dumps({"method": method, "params": params}).encode() + b"\n"
            s.sendall(payload)
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(4096)
                if not chunk:
                    raise RuntimeError("env adapter closed socket mid-response")
                buf += chunk
            return json.loads(buf.split(b"\n", 1)[0].decode())
        finally:
            s.close()
